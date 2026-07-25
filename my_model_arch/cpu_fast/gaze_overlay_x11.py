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

    def fail_callback():
        nonlocal callback_failed
        callback_failed = True
        control_connection.send(("error", traceback.format_exc()))
        timer.stop()
        widget.close()
        app.exit(1)

    def poll_parent():
        try:
            while control_connection.poll():
                message = control_connection.recv()
                if message != ("stop", None):
                    raise RuntimeError(
                        f"unexpected gaze overlay control message: {message!r}"
                    )
                control_connection.send(("stopped", None))
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
        except BaseException:
            fail_callback()

    timer.timeout.connect(poll_parent)
    timer.start(max(1, round(config["update_interval"] * 1000)))
    control_connection.send(("ready", None))
    exit_code = app.exec()
    if exit_code and not callback_failed:
        raise RuntimeError(
            f"X11 gaze overlay event loop exited with code {exit_code}"
        )


def _overlay_process_main(control_connection, point_queue, config):
    try:
        _run_qt_overlay(control_connection, point_queue, config)
    except BaseException:
        control_connection.send(("error", traceback.format_exc()))
    finally:
        control_connection.close()
        point_queue.close()


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
        self._point_queue = None
        self._failure = None
        self._started = False

    def start(self):
        if self._process is not None:
            raise RuntimeError("gaze overlay is already started")
        if self._failure is not None:
            raise self._failure

        context = multiprocessing.get_context("spawn")
        parent_control, child_control = context.Pipe(duplex=True)
        point_queue = context.Queue(maxsize=1)
        process = context.Process(
            target=_overlay_process_main,
            args=(child_control, point_queue, self._config),
        )
        self._process = process
        self._control_connection = parent_control
        self._point_queue = point_queue

        try:
            process.start()
        except BaseException as error:
            self._close_after_start_failure(child_control, error)
            raise
        child_control.close()

        deadline = time.monotonic() + _START_TIMEOUT_SECONDS
        while True:
            message = self._receive_before_deadline(deadline)
            if message is not None:
                if message == ("ready", None):
                    self._started = True
                    return
                self._raise_control_failure(message)

            if not process.is_alive():
                self._raise_unexpected_death()
            if time.monotonic() >= deadline:
                error = TimeoutError(
                    "gaze overlay child did not become ready within 5 seconds"
                )
                self._terminate_failed_process(error)
                raise error

    def update_gaze_position(self, x, y):
        if not self._started:
            raise RuntimeError("gaze overlay is not running")
        self.raise_if_failed()
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

    def raise_if_failed(self):
        if self._failure is not None:
            raise self._failure
        if self._process is None:
            return

        while self._control_connection.poll():
            self._raise_control_failure(self._control_connection.recv())
        if not self._process.is_alive():
            self._raise_unexpected_death()

    def stop(self):
        if self._failure is not None:
            raise self._failure
        if self._process is None:
            return
        self.raise_if_failed()

        try:
            self._control_connection.send(("stop", None))
        except BaseException as error:
            self._terminate_failed_process(error)
            raise

        deadline = time.monotonic() + _STOP_TIMEOUT_SECONDS
        acknowledged = False
        while not acknowledged:
            message = self._receive_before_deadline(deadline)
            if message is not None:
                if message == ("stopped", None):
                    acknowledged = True
                    break
                self._raise_control_failure(message)
            if not self._process.is_alive():
                self._raise_unexpected_death()
            if time.monotonic() >= deadline:
                error = TimeoutError(
                    "gaze overlay child did not acknowledge stop within "
                    "5 seconds"
                )
                self._terminate_failed_process(error)
                raise error

        remaining = max(0.0, deadline - time.monotonic())
        self._process.join(remaining)
        if self._process.is_alive():
            error = TimeoutError(
                "gaze overlay child did not exit within 5 seconds after "
                "stop acknowledgement"
            )
            self._terminate_failed_process(error)
            raise error
        if self._process.exitcode != 0:
            error = RuntimeError(
                "gaze overlay child exited after stop acknowledgement with "
                f"code {self._process.exitcode}"
            )
            self._failure = error
            self._dispose_parent_resources()
            raise error

        self._started = False
        self._dispose_parent_resources()

    def _receive_before_deadline(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        if self._control_connection.poll(
            min(_CONTROL_POLL_SECONDS, remaining)
        ):
            return self._control_connection.recv()
        return None

    def _raise_control_failure(self, message):
        if (
            isinstance(message, tuple)
            and len(message) == 2
            and message[0] == "error"
            and isinstance(message[1], str)
        ):
            error = RuntimeError(
                f"gaze overlay child failed:\n{message[1]}"
            )
        else:
            error = RuntimeError(
                f"unexpected gaze overlay child message: {message!r}"
            )
        self._terminate_failed_process(error)
        raise error

    def _raise_unexpected_death(self):
        exitcode = self._process.exitcode
        error = RuntimeError(
            "gaze overlay child exited unexpectedly with code "
            f"{exitcode}"
        )
        self._failure = error
        self._dispose_parent_resources(error)
        raise error

    def _close_after_start_failure(self, child_control, primary_error):
        try:
            child_control.close()
        except BaseException as cleanup_error:
            primary_error.add_note(
                "gaze overlay child connection cleanup failed with "
                f"{type(cleanup_error).__name__}: {cleanup_error}"
            )
        self._dispose_parent_resources(primary_error)

    def _terminate_failed_process(self, primary_error):
        self._failure = primary_error
        process = self._process
        if process is not None:
            try:
                if process.is_alive():
                    process.terminate()
                process.join(1)
            except BaseException as cleanup_error:
                primary_error.add_note(
                    "gaze overlay child termination failed with "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        self._started = False
        self._dispose_parent_resources(primary_error)

    def _close_point_queue(self, primary_error=None):
        if self._point_queue is None:
            return
        operations = (self._point_queue.close, self._point_queue.join_thread)
        for operation in operations:
            try:
                operation()
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    "gaze overlay point queue cleanup failed with "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )

    def _dispose_parent_resources(self, primary_error=None):
        control_connection = self._control_connection
        if control_connection is not None:
            try:
                control_connection.close()
            except BaseException as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    "gaze overlay control cleanup failed with "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                )
        self._close_point_queue(primary_error)
        self._process = None
        self._control_connection = None
        self._point_queue = None
