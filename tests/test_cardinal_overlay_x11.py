import ctypes.util
from types import SimpleNamespace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from my_model_arch.cpu_fast import cardinal_overlay_x11 as overlay_module
from my_model_arch.cpu_fast.cardinal_overlay_x11 import (
    CardinalOverlay,
    FullscreenCardinalWheel,
)
from my_model_arch.cpu_fast.pipeline import ObserverWithSectorWheel
from my_model_arch.cpu_fast.robot_actions import RobotAction


class FakeOverlay:
    def __init__(self, screen_size):
        self.screen_size = tuple(screen_size)
        self.calls = []

    def start(self):
        self.calls.append(("start", None))

    def show(self, labels):
        self.calls.append(("show", tuple(labels)))

    def select(self, index):
        self.calls.append(("select", index))

    def hide(self):
        self.calls.append(("hide", None))

    def raise_if_failed(self):
        self.calls.append(("raise_if_failed", None))

    def stop(self):
        self.calls.append(("stop", None))


@pytest.mark.parametrize(
    ("logical_size", "device_pixel_ratio", "physical_size"),
    [
        ((1920, 1080), 1.0, (1920, 1080)),
        ((2048, 1080), 2.0, (4096, 2160)),
        ((1536, 864), 1.25, (1920, 1080)),
    ],
)
def test_physical_screen_size_applies_qt_device_pixel_ratio(
    logical_size,
    device_pixel_ratio,
    physical_size,
):
    screen = SimpleNamespace(
        geometry=lambda: SimpleNamespace(
            width=lambda: logical_size[0],
            height=lambda: logical_size[1],
        ),
        devicePixelRatio=lambda: device_pixel_ratio,
    )

    assert overlay_module._physical_screen_size(screen) == (
        logical_size,
        device_pixel_ratio,
        physical_size,
    )


@pytest.mark.parametrize("device_pixel_ratio", [0, -1, float("nan")])
def test_physical_screen_size_rejects_invalid_qt_scale(
    device_pixel_ratio,
):
    screen = SimpleNamespace(
        geometry=lambda: SimpleNamespace(
            width=lambda: 1920,
            height=lambda: 1080,
        ),
        devicePixelRatio=lambda: device_pixel_ratio,
    )

    with pytest.raises(RuntimeError, match="device pixel ratio"):
        overlay_module._physical_screen_size(screen)


def _wheel(monkeypatch, screen_size=(3840, 2160)):
    created = []

    def make_overlay(size):
        overlay = FakeOverlay(size)
        created.append(overlay)
        return overlay

    monkeypatch.setattr(overlay_module, "CardinalOverlay", make_overlay)
    subject = SimpleNamespace(
        screen_size=screen_size,
        op_xy_generation=0,
        published_op_xy_generation=0,
        op_xy=(None, None),
    )
    return FullscreenCardinalWheel(subject), subject, created[0]


@pytest.mark.parametrize(
    ("point", "expected_index"),
    [
        ((1920, 1), 0),
        ((1920, 2159), 1),
        ((1, 1080), 2),
        ((3839, 1080), 3),
        ((1000, 200), 0),
        ((2840, 1960), 1),
        ((1920, 1080), None),
    ],
)
def test_fullscreen_wheel_maps_the_entire_screen_by_normalized_direction(
    monkeypatch, point, expected_index
):
    wheel, _, _ = _wheel(monkeypatch)

    assert (
        wheel.get_cardinal_from_screen_position(*point) == expected_index
    )


def test_fullscreen_wheel_shows_chinese_labels_and_tracks_latest_gaze(
    monkeypatch,
):
    wheel, subject, overlay = _wheel(monkeypatch)
    actions = (
        RobotAction("move_forward_step", "前进一步", "wheel"),
        RobotAction("move_backward_step", "后退一步", "wheel"),
        RobotAction("turn_left", "左转", "wheel"),
        RobotAction("turn_right", "右转", "wheel"),
    )

    wheel.start()
    wheel.update_categories(actions)
    subject.op_xy = (20, 1080)
    subject.published_op_xy_generation = 1
    wheel.check_op_xy()
    wheel.hide()
    wheel.stop()

    assert wheel.selected_sector is actions[2]
    assert overlay.calls == [
        ("start", None),
        ("show", ("前进一步", "后退一步", "左转", "右转")),
        ("select", 2),
        ("hide", None),
        ("stop", None),
    ]


def test_fullscreen_wheel_rejects_non_cardinal_or_incomplete_categories(
    monkeypatch,
):
    wheel, _, _ = _wheel(monkeypatch)

    with pytest.raises(
        ValueError,
        match="only supports cardinal layout",
    ):
        wheel.update_categories(["a", "b", "c", "d"], layout_type="circle")
    with pytest.raises(
        ValueError,
        match="requires exactly four categories",
    ):
        wheel.update_categories(["a", "b", "c"])


def test_robot_observer_uses_fullscreen_overlay_without_creating_tk(
    monkeypatch,
):
    events = []
    subject = SimpleNamespace(
        action_output="robot_terminal",
        screen_size=(1920, 1080),
        op_xy_generation=0,
        published_op_xy_generation=0,
        quit=False,
    )

    class RunOnceWheel:
        def __init__(self, received_subject):
            assert received_subject is subject
            events.append("construct")

        def start(self):
            events.append("start")
            subject.quit = True

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(
        overlay_module,
        "FullscreenCardinalWheel",
        RunOnceWheel,
    )
    wheel = ObserverWithSectorWheel(
        subject,
        layout="fullscreen_cardinal",
    )
    wheel.should_run = True

    wheel.run_sector_wheel()

    assert events == ["construct", "start", "stop"]
    assert wheel._worker_error is None


def _require_qt_xcb_dependencies():
    if ctypes.util.find_library("xcb-cursor") is None:
        pytest.skip("libxcb-cursor0 is required for Qt's xcb plugin")


@pytest.mark.x11
def test_widget_is_transparent_click_through_fullscreen_overlay():
    _require_qt_xcb_dependencies()
    app = QApplication.instance() or QApplication([])
    widget = overlay_module._CardinalOverlayWidget()
    flags = widget.windowFlags()

    assert widget.testAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground
    )
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.WindowTransparentForInput
    assert flags & Qt.WindowType.WindowDoesNotAcceptFocus

    widget.show_categories(("前进一步", "后退一步", "左转", "右转"))
    widget.select(3)
    app.processEvents()
    assert widget._labels == ("前进一步", "后退一步", "左转", "右转")
    assert widget._selected_index == 3
    widget.close()
    app.processEvents()


@pytest.mark.x11
def test_start_fails_visibly_without_x11_compositor():
    if overlay_module._x11_compositor_owner_exists():
        pytest.skip("requires an isolated X11 display without a compositor")
    overlay = CardinalOverlay((1280, 720))

    with pytest.raises(
        RuntimeError,
        match="X11 compositing manager is required",
    ):
        overlay.start()


@pytest.mark.x11
def test_overlay_show_select_hide_and_stop_with_compositor():
    if not overlay_module._x11_compositor_owner_exists():
        pytest.skip("xcompmgr is required for the positive X11 integration")
    _require_qt_xcb_dependencies()
    app = QApplication.instance() or QApplication([])
    screen = app.primaryScreen()
    if screen is None:
        pytest.fail("X11 test has no primary screen")
    _, _, physical_size = overlay_module._physical_screen_size(screen)
    overlay = CardinalOverlay(physical_size)

    overlay.start()
    try:
        overlay.show(("前进一步", "后退一步", "左转", "右转"))
        overlay.select(2)
        overlay.hide()
        overlay.raise_if_failed()
    finally:
        overlay.stop()
