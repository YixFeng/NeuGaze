import math
import multiprocessing
import traceback

from PySide6.QtCore import QPointF, QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QWidget

from .gaze_overlay_x11 import _x11_compositor_owner_exists


_START_TIMEOUT_SECONDS = 5.0
_STOP_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_MS = 16
_SELECTION_STABLE_FRAMES = 5
_NEUTRAL_RELEASE_STABLE_FRAMES = 3
_CONFIRMATION_STABLE_FRAMES = 5


def _physical_screen_size(screen):
    geometry = screen.geometry()
    logical_size = (geometry.width(), geometry.height())
    device_pixel_ratio = float(screen.devicePixelRatio())
    if not math.isfinite(device_pixel_ratio) or device_pixel_ratio <= 0:
        raise RuntimeError(
            "robot action overlay received invalid Qt device pixel ratio: "
            f"{device_pixel_ratio!r}"
        )
    physical_size = tuple(
        round(dimension * device_pixel_ratio)
        for dimension in logical_size
    )
    return logical_size, device_pixel_ratio, physical_size


class _CardinalOverlayWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._labels = ()
        self._selected_index = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )

    def show_categories(self, labels):
        if len(labels) != 4:
            raise ValueError("cardinal overlay requires exactly four labels")
        self._labels = tuple(labels)
        self._selected_index = None
        self.showFullScreen()
        self.update()

    def select(self, index):
        if index is not None and index not in range(4):
            raise ValueError(f"invalid cardinal overlay selection: {index!r}")
        if index == self._selected_index:
            return
        self._selected_index = index
        self.update()

    def paintEvent(self, event):
        if not self._labels:
            return

        width = float(self.width())
        height = float(self.height())
        center = QPointF(width / 2, height / 2)
        polygons = (
            QPolygonF((QPointF(0, 0), QPointF(width, 0), center)),
            QPolygonF((QPointF(0, height), center, QPointF(width, height))),
            QPolygonF((QPointF(0, 0), center, QPointF(0, height))),
            QPolygonF((QPointF(width, 0), QPointF(width, height), center)),
        )
        label_centers = (
            QPointF(width / 2, height * 0.16),
            QPointF(width / 2, height * 0.84),
            QPointF(width * 0.14, height / 2),
            QPointF(width * 0.86, height / 2),
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        for index, polygon in enumerate(polygons):
            if index == self._selected_index:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(37, 99, 235, 54))
                painter.drawPolygon(polygon)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 105), 2))
        for corner in (
            QPointF(0, 0),
            QPointF(width, 0),
            QPointF(0, height),
            QPointF(width, height),
        ):
            painter.drawLine(corner, center)

        font_size = max(24, min(40, round(height / 30)))
        font = QFont("Noto Sans CJK SC", font_size, QFont.Weight.DemiBold)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        horizontal_padding = font_size
        vertical_padding = round(font_size * 0.55)

        for index, (label, label_center) in enumerate(
            zip(self._labels, label_centers)
        ):
            text_rect = metrics.boundingRect(label)
            panel = QRectF(
                label_center.x()
                - text_rect.width() / 2
                - horizontal_padding,
                label_center.y()
                - text_rect.height() / 2
                - vertical_padding,
                text_rect.width() + 2 * horizontal_padding,
                text_rect.height() + 2 * vertical_padding,
            )
            selected = index == self._selected_index
            painter.setPen(
                QPen(
                    QColor(147, 197, 253, 230)
                    if selected
                    else QColor(255, 255, 255, 70),
                    2,
                )
            )
            painter.setBrush(
                QColor(30, 64, 175, 225)
                if selected
                else QColor(17, 24, 39, 190)
            )
            painter.drawRoundedRect(
                panel,
                font_size * 0.45,
                font_size * 0.45,
            )
            painter.setPen(QColor(255, 255, 255, 255))
            painter.drawText(
                panel,
                Qt.AlignmentFlag.AlignCenter,
                label,
            )


def _run_overlay(control_connection, expected_screen_size):
    if not _x11_compositor_owner_exists():
        raise RuntimeError(
            "X11 compositing manager is required for robot action overlay"
        )

    app = QApplication([])
    screen = app.primaryScreen()
    if screen is None:
        raise RuntimeError("robot action overlay has no primary X11 screen")
    geometry = screen.geometry()
    logical_size, device_pixel_ratio, physical_size = (
        _physical_screen_size(screen)
    )
    if physical_size != tuple(expected_screen_size):
        raise RuntimeError(
            "robot action overlay screen mismatch: "
            f"pipeline={tuple(expected_screen_size)!r}, "
            f"Qt logical={logical_size!r}, "
            f"Qt devicePixelRatio={device_pixel_ratio!r}, "
            f"Qt physical={physical_size!r}"
        )

    widget = _CardinalOverlayWidget()
    widget.setGeometry(geometry)
    widget.hide()
    timer = QTimer()
    callback_traceback = None
    stop_requested = False

    def fail_callback():
        nonlocal callback_traceback
        callback_traceback = traceback.format_exc()
        timer.stop()
        widget.close()
        app.exit(1)

    def poll_parent():
        nonlocal stop_requested
        try:
            while control_connection.poll():
                command, payload = control_connection.recv()
                if command == "show":
                    widget.show_categories(payload)
                elif command == "select":
                    widget.select(payload)
                elif command == "hide":
                    if payload is not None:
                        raise RuntimeError(
                            f"hide payload must be None, got {payload!r}"
                        )
                    widget.hide()
                elif command == "stop":
                    if payload is not None:
                        raise RuntimeError(
                            f"stop payload must be None, got {payload!r}"
                        )
                    stop_requested = True
                    timer.stop()
                    widget.close()
                    app.quit()
                    return
                else:
                    raise RuntimeError(
                        "unexpected robot action overlay command: "
                        f"{(command, payload)!r}"
                    )
        except BaseException:
            fail_callback()

    timer.timeout.connect(poll_parent)
    timer.start(_POLL_INTERVAL_MS)
    control_connection.send(("ready", physical_size))
    exit_code = app.exec()
    if callback_traceback is not None:
        return callback_traceback
    if exit_code:
        raise RuntimeError(
            f"robot action overlay event loop exited with code {exit_code}"
        )
    if not stop_requested:
        raise RuntimeError(
            "robot action overlay event loop exited before stop"
        )
    return None


def _overlay_process_main(control_connection, expected_screen_size):
    formatted_traceback = None
    try:
        formatted_traceback = _run_overlay(
            control_connection, expected_screen_size
        )
    except BaseException:
        formatted_traceback = traceback.format_exc()

    try:
        if formatted_traceback is None:
            control_connection.send(("stopped", None))
        else:
            control_connection.send(("error", formatted_traceback))
    finally:
        control_connection.close()


class CardinalOverlay:
    def __init__(self, screen_size):
        self._screen_size = tuple(screen_size)
        self._process = None
        self._control_connection = None
        self._child_control_connection = None
        self._failure = None
        self._started = False

    def start(self):
        if self._process is not None:
            raise RuntimeError("robot action overlay is already started")
        if self._failure is not None:
            raise self._failure

        context = multiprocessing.get_context("spawn")
        parent_control, child_control = context.Pipe(duplex=True)
        process = context.Process(
            target=_overlay_process_main,
            args=(child_control, self._screen_size),
        )
        self._control_connection = parent_control
        self._child_control_connection = child_control
        self._process = process
        try:
            process.start()
            child_control.close()
            self._child_control_connection = None
            if not parent_control.poll(_START_TIMEOUT_SECONDS):
                raise TimeoutError(
                    "robot action overlay did not become ready within "
                    f"{_START_TIMEOUT_SECONDS:.1f}s"
                )
            message = parent_control.recv()
            if message[0] == "error":
                raise RuntimeError(
                    "robot action overlay failed to start:\n" + message[1]
                )
            if message != ("ready", self._screen_size):
                raise RuntimeError(
                    "unexpected robot action overlay startup message: "
                    f"{message!r}"
                )
            self._started = True
        except BaseException as error:
            self._failure = error
            self._close_failed_start()
            raise

    def _close_failed_start(self):
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(_STOP_TIMEOUT_SECONDS)
            if process.is_alive():
                process.kill()
                process.join(_STOP_TIMEOUT_SECONDS)
        for connection in (
            self._child_control_connection,
            self._control_connection,
        ):
            if connection is not None:
                connection.close()
        if process is not None:
            process.close()
        self._process = None
        self._control_connection = None
        self._child_control_connection = None
        self._started = False

    def _send(self, command, payload):
        self.raise_if_failed()
        if not self._started:
            raise RuntimeError("robot action overlay is not started")
        self._control_connection.send((command, payload))
        self.raise_if_failed()

    def show(self, labels):
        self._send("show", tuple(labels))

    def select(self, index):
        self._send("select", index)

    def hide(self):
        self._send("hide", None)

    def raise_if_failed(self):
        if self._failure is not None:
            raise self._failure
        if not self._started:
            return
        if self._control_connection.poll():
            message = self._control_connection.recv()
            if message[0] == "error":
                self._failure = RuntimeError(
                    "robot action overlay failed:\n" + message[1]
                )
            else:
                self._failure = RuntimeError(
                    "unexpected robot action overlay message: "
                    f"{message!r}"
                )
        elif not self._process.is_alive():
            self._failure = RuntimeError(
                "robot action overlay process exited unexpectedly with code "
                f"{self._process.exitcode}"
            )
        if self._failure is not None:
            raise self._failure

    def stop(self):
        if self._process is None:
            if self._failure is not None:
                raise self._failure
            return

        error = None
        try:
            self.raise_if_failed()
            self._control_connection.send(("stop", None))
            if not self._control_connection.poll(_STOP_TIMEOUT_SECONDS):
                raise TimeoutError(
                    "robot action overlay did not stop within "
                    f"{_STOP_TIMEOUT_SECONDS:.1f}s"
                )
            message = self._control_connection.recv()
            if message[0] == "error":
                raise RuntimeError(
                    "robot action overlay failed while stopping:\n"
                    + message[1]
                )
            if message != ("stopped", None):
                raise RuntimeError(
                    "unexpected robot action overlay stop message: "
                    f"{message!r}"
                )
        except BaseException as caught:
            error = caught

        process = self._process
        process.join(_STOP_TIMEOUT_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join(_STOP_TIMEOUT_SECONDS)
        if process.is_alive():
            process.kill()
            process.join(_STOP_TIMEOUT_SECONDS)
        self._control_connection.close()
        process.close()
        self._process = None
        self._control_connection = None
        self._started = False
        if error is not None:
            self._failure = error
            raise error


class FullscreenCardinalWheel:
    def __init__(
        self,
        subject,
        yaw_threshold_degrees,
        pitch_threshold_degrees,
    ):
        self.subject = subject
        self.screen_width, self.screen_height = subject.screen_size
        if self.screen_width <= 0 or self.screen_height <= 0:
            raise ValueError(
                "fullscreen cardinal wheel requires a positive screen size"
            )
        self.yaw_threshold_degrees = float(yaw_threshold_degrees)
        self.pitch_threshold_degrees = float(pitch_threshold_degrees)
        for field_name, value in (
            ("yaw_threshold_degrees", self.yaw_threshold_degrees),
            ("pitch_threshold_degrees", self.pitch_threshold_degrees),
        ):
            if not math.isfinite(value) or not 0 < value <= 45:
                raise ValueError(
                    f"{field_name} must be finite and in the interval (0, 45]"
                )
        self.categories = ()
        self.selected_sector = None
        self._selected_index = None
        self._candidate_index = None
        self._candidate_frames = 0
        self._neutral_release_frames = 0
        self._confirmation_frames = 0
        self._confirmation_armed = False
        self._overlay = CardinalOverlay(subject.screen_size)

    def start(self):
        self._overlay.start()

    def update_categories(self, categories, layout_type="cardinal"):
        if layout_type != "cardinal":
            raise ValueError(
                "fullscreen robot wheel only supports cardinal layout"
            )
        if len(categories) != 4:
            raise ValueError(
                "fullscreen cardinal wheel requires exactly four categories"
            )
        self.categories = tuple(categories)
        self.selected_sector = None
        self._selected_index = None
        self._candidate_index = None
        self._candidate_frames = 0
        self._neutral_release_frames = 0
        self._confirmation_frames = 0
        self._confirmation_armed = False
        self._overlay.show(
            tuple(
                category.label
                if hasattr(category, "label")
                else str(category)
                for category in self.categories
            )
        )

    def get_cardinal_from_head_pose(self, pitch, yaw):
        pitch = float(pitch)
        yaw = float(yaw)
        if not math.isfinite(pitch) or not math.isfinite(yaw):
            raise RuntimeError(
                f"head pose must be finite, got pitch={pitch!r}, yaw={yaw!r}"
            )
        pitch_ratio = abs(pitch) / self.pitch_threshold_degrees
        yaw_ratio = abs(yaw) / self.yaw_threshold_degrees
        if pitch_ratio < 1 and yaw_ratio < 1:
            return None
        if pitch_ratio >= yaw_ratio:
            return 0 if pitch > 0 else 1
        return 2 if yaw > 0 else 3

    def observe_control_frame(
        self,
        *,
        face_detected,
        opener_active,
        pitch,
        yaw,
    ):
        if not face_detected:
            self._candidate_index = None
            self._candidate_frames = 0
            self._neutral_release_frames = 0
            self._confirmation_frames = 0
            self._confirmation_armed = False
            self._overlay.raise_if_failed()
            return None
        if not isinstance(opener_active, bool):
            raise TypeError(
                "wheel opener state must be bool when a face is detected"
            )

        index = self.get_cardinal_from_head_pose(pitch, yaw)
        if index is not None:
            self._neutral_release_frames = 0
            self._confirmation_frames = 0
            self._confirmation_armed = False
            if index == self._candidate_index:
                self._candidate_frames += 1
            else:
                self._candidate_index = index
                self._candidate_frames = 1
            if self._candidate_frames >= _SELECTION_STABLE_FRAMES:
                if index != self._selected_index:
                    self._selected_index = index
                    self.selected_sector = self.categories[index]
                    self._overlay.select(index)
                else:
                    self._overlay.raise_if_failed()
            else:
                self._overlay.raise_if_failed()
            return None

        self._candidate_index = None
        self._candidate_frames = 0
        if not opener_active:
            self._neutral_release_frames += 1
            self._confirmation_frames = 0
            if (
                self._neutral_release_frames
                >= _NEUTRAL_RELEASE_STABLE_FRAMES
            ):
                self._confirmation_armed = True
            self._overlay.raise_if_failed()
            return None

        self._neutral_release_frames = 0
        if not self._confirmation_armed:
            self._confirmation_frames = 0
            self._overlay.raise_if_failed()
            return None

        self._confirmation_frames += 1
        if self._confirmation_frames >= _CONFIRMATION_STABLE_FRAMES:
            if self.selected_sector is None:
                return "cancel"
            return "submit"
        self._overlay.raise_if_failed()
        return None

    def hide(self):
        self._overlay.hide()

    def stop(self):
        self._overlay.stop()
