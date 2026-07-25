import ctypes.util
import time

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from my_model_arch.cpu_fast import gaze_overlay_x11 as overlay_module
from my_model_arch.cpu_fast.gaze_overlay_x11 import GazeOverlay


def _require_qt_xcb_dependencies():
    if ctypes.util.find_library("xcb-cursor") is None:
        pytest.skip("libxcb-cursor0 is required for Qt's xcb plugin")


@pytest.mark.x11
def test_x11_widget_is_translucent_click_through_and_nonactivating():
    _require_qt_xcb_dependencies()
    app = QApplication.instance() or QApplication([])
    widget = overlay_module._GazeOverlayWidget(
        {
            "history_duration": 0.15,
            "point_radius": 12,
            "point_alpha": 100,
            "color_r": 230,
            "color_g": 20,
            "color_b": 20,
            "gaussian_sigma_ratio": 1.0,
            "window_alpha": 100,
        }
    )
    flags = widget.windowFlags()

    assert widget.testAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground
    )
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus

    widget.close()
    app.processEvents()


@pytest.mark.x11
def test_start_fails_visibly_when_x11_compositor_owner_is_missing():
    if overlay_module._x11_compositor_owner_exists():
        pytest.skip("requires an isolated X11 display without a compositor")
    overlay = GazeOverlay()

    with pytest.raises(
        RuntimeError,
        match="X11 compositing manager is required for gaze overlay",
    ):
        overlay.start()


@pytest.mark.x11
def test_overlay_handshake_update_and_synchronous_stop_with_compositor():
    if not overlay_module._x11_compositor_owner_exists():
        pytest.skip("xcompmgr is required for the positive X11 integration")
    overlay = GazeOverlay()
    _require_qt_xcb_dependencies()

    overlay.start()
    try:
        overlay.update_gaze_position(80, 90)
        overlay.update_gaze_position(100, 110)
        time.sleep(0.05)
        overlay.raise_if_failed()
    finally:
        overlay.stop()
