import ctypes
import math
import multiprocessing
import queue
import time
import traceback
from collections import deque

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget


_START_TIMEOUT_SECONDS = 5.0
_STOP_TIMEOUT_SECONDS = 5.0
_QUEUE_HANDOFF_TIMEOUT_SECONDS = 0.05
_CONTROL_POLL_SECONDS = 0.05


def _x11_compositor_owner_exists():
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XInternAtom.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x11.XGetSelectionOwner.restype = ctypes.c_ulong
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int

    display = x11.XOpenDisplay(None)
    if not display:
        return False
    try:
        atom = x11.XInternAtom(display, b"_NET_WM_CM_S0", True)
        return bool(atom and x11.XGetSelectionOwner(display, atom))
    finally:
        x11.XCloseDisplay(display)



class _GazeOverlayWidget(QWidget):
    def __init__(self, config):
        super().__init__()
        self._history_duration = config["history_duration"]
        self._point_radius = config["point_radius"]
        self._point_alpha = config["point_alpha"]
        self._color = (
            config["color_r"], config["color_g"], config["color_b"]
        )
        self._gaussian_sigma_ratio = config["gaussian_sigma_ratio"]
        self._window_alpha = config["window_alpha"]
        self._history = deque()

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def update_gaze_position(self, x, y):
        now = time.monotonic()
        self._history.append((int(x), int(y), now))
        self._discard_expired_points(now)
        self.update()

    def advance_history(self):
        if not self._history:
            return
        self._discard_expired_points(time.monotonic())
        self.update()

    def _discard_expired_points(self, now):
        oldest_allowed = now - self._history_duration
        while self._history and self._history[0][2] < oldest_allowed:
            self._history.popleft()

    def paintEvent(self, event):
        now = time.monotonic()
        self._discard_expired_points(now)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        radius = float(self._point_radius)
        sigma = radius / self._gaussian_sigma_ratio
        base_alpha = self._point_alpha * self._window_alpha / 255
        red, green, blue = self._color
        for x, y, timestamp in self._history:
            remaining = max(
                0.0,
                1.0 - (now - timestamp) / self._history_duration,
            )
            gradient = QRadialGradient(QPointF(x, y), radius)
            for step in range(5):
                distance_ratio = step / 4
                distance = distance_ratio * radius
                intensity = math.exp(
                    -(distance * distance) / (2 * sigma * sigma)
                )
                intensity *= intensity
                alpha = round(base_alpha * remaining * intensity)
                gradient.setColorAt(
                    distance_ratio,
                    QColor(red, green, blue, alpha),
                )
            gradient.setColorAt(1.0, QColor(red, green, blue, 0))
            painter.setBrush(QBrush(gradient))
            painter.drawEllipse(
                QRectF(
                    x - radius,
                    y - radius,
                    radius * 2,
                    radius * 2,
                )
            )


def _run_qt_overlay(control_connection, point_queue, config):
    if not _x11_compositor_owner_exists():
        raise RuntimeError(
            "X11 compositing manager is required for gaze overlay"
        )
    app = QApplication([])
    widget = _GazeOverlayWidget(config)
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("X11 gaze overlay has no primary screen")
    widget.setGeometry(screen.geometry())
    widget.showFullScreen()

    timer = QTimer()
    callback_failed = False
    stop_requested = False

    def fail_callback():
        nonlocal callback_failed
        callback_failed = True
        formatted_traceback = traceback.format_exc()
        shutdown_failures = []
        for label, operation in (
            ("timer stop", timer.stop),
            ("widget close", widget.close),
            ("application exit", lambda: app.exit(1)),
        ):
            try:
                operation()
            except BaseException:
                shutdown_failures.append((label, traceback.format_exc()))
        for label, shutdown_traceback in shutdown_failures:
            formatted_traceback += (
                f"\nDuring gaze overlay {label}:\n{shutdown_traceback}"
            )
        control_connection.send(("error", formatted_traceback))

    def poll_parent():
        nonlocal stop_requested
        try:
            while control_connection.poll():
                message = control_connection.recv()
                if message != ("stop", None):
                    raise RuntimeError(
                        f"unexpected gaze overlay control message: {message!r}"
                    )
                stop_requested = True
                timer.stop()
                widget.close()
                app.quit()
                return

            latest_point = None
            while True:
                try:
                    latest_point = point_queue.get_nowait()
                except queue.Empty:
                    break
            if latest_point is not None:
                widget.update_gaze_position(*latest_point)
            else:
                widget.advance_history()
        except BaseException:
            fail_callback()

    timer.timeout.connect(poll_parent)
    timer.start(max(1, round(config["update_interval"] * 1000)))
    control_connection.send(("ready", None))
    exit_code = app.exec()
    if callback_failed:
        return False
    if exit_code:
        raise RuntimeError(
            f"X11 gaze overlay event loop exited with code {exit_code}"
        )
    if not stop_requested:
        raise RuntimeError("X11 gaze overlay event loop exited before stop")
    return True


def _overlay_process_main(control_connection, point_queue, config):
    try:
        stopped = _run_qt_overlay(control_connection, point_queue, config)
    except BaseException:
        formatted_traceback = traceback.format_exc()
        try:
            point_queue.close()
        except BaseException:
            formatted_traceback += (
                "\nDuring gaze overlay queue cleanup:\n"
                + traceback.format_exc()
            )
        control_connection.send(("error", formatted_traceback))
    else:
        try:
            point_queue.close()
        except BaseException:
            control_connection.send(("error", traceback.format_exc()))
        else:
            if stopped:
                control_connection.send(("stopped", None))
    finally:
        control_connection.close()


class GazeOverlay:
    def __init__(
        self,
        history_duration=0.15,
        update_interval=0.016,
        point_radius=12,
        point_alpha=100,
        clear_radius=55,
        color_r=230,
        color_g=20,
        color_b=20,
        gaussian_sigma_ratio=1.0,
        window_alpha=100,
    ):
        self._config = {
            "history_duration": history_duration,
            "update_interval": update_interval,
            "point_radius": point_radius,
            "point_alpha": point_alpha,
            "clear_radius": clear_radius,
            "color_r": color_r,
            "color_g": color_g,
            "color_b": color_b,
            "gaussian_sigma_ratio": gaussian_sigma_ratio,
            "window_alpha": window_alpha,
        }
        self._process = None
        self._control_connection = None
        self._child_control_connection = None
        self._point_queue = None
        self._failure = None
        self._started = False

    def start(self):
        if self._process is not None:
            raise RuntimeError("gaze overlay is already started")
        if self._failure is not None:
            raise self._failure

        try:
            context = multiprocessing.get_context("spawn")
            parent_control, child_control = context.Pipe(duplex=True)
            self._control_connection = parent_control
            self._child_control_connection = child_control
            self._point_queue = context.Queue(maxsize=1)
            self._process = context.Process(
                target=_overlay_process_main,
                args=(child_control, self._point_queue, self._config),
            )
            self._process.start()
            self._child_control_connection.close()
            self._child_control_connection = None

            deadline = time.monotonic() + _START_TIMEOUT_SECONDS
            while True:
                message = self._receive_before_deadline(deadline)
                if message is not None:
                    if message == ("ready", None):
                        self._started = True
                        return
                    raise self._control_message_error(message)

                if not self._process.is_alive():
                    raise self._unexpected_death_error()
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "gaze overlay child did not become ready within "
                        "5 seconds"
                    )
        except BaseException as error:
            self._fail_and_cleanup(error)
            raise

    def update_gaze_position(self, x, y):
        if not self._started:
            raise RuntimeError("gaze overlay is not running")
        self.raise_if_failed()
        try:
            point = (int(x), int(y))
            try:
                self._point_queue.put_nowait(point)
            except queue.Full:
                try:
                    self._point_queue.get(
                        timeout=_QUEUE_HANDOFF_TIMEOUT_SECONDS
                    )
                except queue.Empty:
                    pass
                self._point_queue.put_nowait(point)
        except BaseException as error:
            self._fail_and_cleanup(error)
            raise

    def raise_if_failed(self):
        if self._failure is not None:
            raise self._failure
        if self._process is None:
            return

        try:
            while self._control_connection.poll():
                message = self._control_connection.recv()
                raise self._control_message_error(message)
            if not self._process.is_alive():
                raise self._unexpected_death_error()
        except BaseException as error:
            self._fail_and_cleanup(error)
            raise

    def stop(self):
        if self._failure is not None:
            raise self._failure
        if self._process is None:
            return

        try:
            self.raise_if_failed()
            self._control_connection.send(("stop", None))

            deadline = time.monotonic() + _STOP_TIMEOUT_SECONDS
            while True:
                message = self._receive_before_deadline(deadline)
                if message is not None:
                    if message == ("stopped", None):
                        break
                    raise self._control_message_error(message)
                if not self._process.is_alive():
                    raise self._unexpected_death_error()
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "gaze overlay child did not acknowledge stop within "
                        "5 seconds"
                    )

            remaining = max(0.0, deadline - time.monotonic())
            self._process.join(remaining)
            if self._process.is_alive():
                raise TimeoutError(
                    "gaze overlay child acknowledged stop but did not exit "
                    "within 5 seconds"
                )

            # Queued messages precede EOF after the acknowledged child exits.
            # Earlier EOF remains a transport failure in start/runtime/stop.
            while self._control_connection.poll():
                try:
                    message = self._control_connection.recv()
                except EOFError:
                    break
                raise self._control_message_error(message)

            if self._process.exitcode != 0:
                raise RuntimeError(
                    "gaze overlay child exited after stop acknowledgement "
                    f"with code {self._process.exitcode}"
                )

            self._started = False
            self._cleanup_resources()
        except BaseException as error:
            self._fail_and_cleanup(error)
            raise

    def _receive_before_deadline(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        if self._control_connection.poll(
            min(_CONTROL_POLL_SECONDS, remaining)
        ):
            return self._control_connection.recv()
        return None

    def _control_message_error(self, message):
        if (
            isinstance(message, tuple)
            and len(message) == 2
            and message[0] == "error"
            and isinstance(message[1], str)
        ):
            return RuntimeError(
                f"gaze overlay child failed:\n{message[1]}"
            )
        return RuntimeError(
            f"unexpected gaze overlay child message: {message!r}"
        )

    def _unexpected_death_error(self):
        return RuntimeError(
            "gaze overlay child exited unexpectedly with code "
            f"{self._process.exitcode}"
        )

    def _fail_and_cleanup(self, primary_error):
        self._failure = primary_error
        self._started = False
        self._cleanup_resources(primary_error, terminate=True)

    def _cleanup_resources(self, primary_error=None, *, terminate=False):
        cleanup_errors = []

        def attempt(label, operation):
            try:
                operation()
            except BaseException as cleanup_error:
                cleanup_errors.append((label, cleanup_error))
                return False
            return True

        process = self._process
        if process is not None:
            alive = None
            try:
                alive = process.is_alive()
            except BaseException as cleanup_error:
                cleanup_errors.append(
                    (
                        "child state check",
                        cleanup_error,
                    )
                )

            if terminate and alive:
                attempt("child terminate", process.terminate)
                attempt(
                    "child join after terminate",
                    lambda: process.join(1),
                )
                try:
                    alive = process.is_alive()
                except BaseException as cleanup_error:
                    cleanup_errors.append(
                        ("child state check after terminate", cleanup_error)
                    )

                if alive:
                    kill = getattr(process, "kill", None)
                    if callable(kill):
                        attempt("child kill", kill)
                        attempt(
                            "child join after kill",
                            lambda: process.join(1),
                        )
                    else:
                        cleanup_errors.append(
                            (
                                "child kill",
                                RuntimeError("process.kill is unavailable"),
                            )
                        )
                    try:
                        alive = process.is_alive()
                    except BaseException as cleanup_error:
                        cleanup_errors.append(
                            ("child state check after kill", cleanup_error)
                        )

            if alive:
                cleanup_errors.append(
                    (
                        "child cleanup",
                        RuntimeError("gaze overlay child remains alive"),
                    )
                )
            elif alive is False:
                if attempt("child process close", process.close):
                    self._process = None

        child_control = self._child_control_connection
        if child_control is not None:
            if attempt("child control close", child_control.close):
                self._child_control_connection = None

        control = self._control_connection
        if control is not None:
            if attempt("parent control close", control.close):
                self._control_connection = None

        point_queue = self._point_queue
        if point_queue is not None:
            queue_closed = attempt("point queue close", point_queue.close)
            queue_joined = attempt("point queue join", point_queue.join_thread)
            if queue_closed and queue_joined:
                self._point_queue = None

        if not cleanup_errors:
            return

        raise_cleanup_error = primary_error is None
        if raise_cleanup_error:
            first_label, primary_error = cleanup_errors.pop(0)
            primary_error.add_note(
                f"gaze overlay cleanup operation failed: {first_label}"
            )

        for label, cleanup_error in cleanup_errors:
            primary_error.add_note(
                f"gaze overlay {label} failed with "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        if raise_cleanup_error:
            raise primary_error
