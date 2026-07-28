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


def _wheel(
    monkeypatch,
    screen_size=(3840, 2160),
    yaw_threshold_degrees=12.0,
    pitch_threshold_degrees=10.0,
):
    created = []

    def make_overlay(size):
        overlay = FakeOverlay(size)
        created.append(overlay)
        return overlay

    monkeypatch.setattr(overlay_module, "CardinalOverlay", make_overlay)
    subject = SimpleNamespace(
        screen_size=screen_size,
        head_angles={"pitch": 0.0, "yaw": 0.0},
    )
    return (
        FullscreenCardinalWheel(
            subject,
            yaw_threshold_degrees=yaw_threshold_degrees,
            pitch_threshold_degrees=pitch_threshold_degrees,
        ),
        subject,
        created[0],
    )


@pytest.mark.parametrize(
    ("head_pose", "expected_index"),
    [
        ((10.0, 0.0), 0),
        ((-10.0, 0.0), 1),
        ((0.0, 12.0), 2),
        ((0.0, -12.0), 3),
        ((9.9, 11.9), None),
        ((15.0, 12.1), 0),
        ((10.1, 18.0), 2),
    ],
)
def test_fullscreen_wheel_maps_head_pose_with_neutral_dead_zone(
    monkeypatch, head_pose, expected_index
):
    wheel, _, _ = _wheel(monkeypatch)

    assert wheel.get_cardinal_from_head_pose(*head_pose) == expected_index

def test_wider_pitch_dead_zone_preserves_left_and_right_selection(
    monkeypatch,
):
    wheel, _, _ = _wheel(
        monkeypatch,
        yaw_threshold_degrees=12.0,
        pitch_threshold_degrees=18.0,
    )

    assert wheel.get_cardinal_from_head_pose(17.9, 0.0) is None
    assert wheel.get_cardinal_from_head_pose(-17.9, 0.0) is None
    assert wheel.get_cardinal_from_head_pose(18.0, 0.0) == 0
    assert wheel.get_cardinal_from_head_pose(-18.0, 0.0) == 1
    assert wheel.get_cardinal_from_head_pose(14.0, 13.0) == 2
    assert wheel.get_cardinal_from_head_pose(14.0, -13.0) == 3


def test_fullscreen_wheel_requires_stable_selection_and_explicit_close(
    monkeypatch,
):
    wheel, _, overlay = _wheel(monkeypatch)
    actions = (
        RobotAction("move_forward_step", "前进一步", "wheel"),
        RobotAction("move_backward_step", "后退一步", "wheel"),
        RobotAction("turn_left", "左转", "wheel"),
        RobotAction("turn_right", "右转", "wheel"),
    )

    wheel.start()
    wheel.update_categories(actions)
    for _ in range(4):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=14.0,
        ) is None
    assert wheel.selected_sector is None

    assert wheel.observe_control_frame(
        face_detected=True,
        mouth_open_recognized=False,
        jaw_open=0.05,
        pitch=0.0,
        yaw=14.0,
    ) is None
    assert wheel.selected_sector is actions[2]

    for _ in range(3):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=True,
            jaw_open=0.7,
            pitch=0.0,
            yaw=0.0,
        ) is None
    for _ in range(4):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=0.0,
        ) is None
    assert wheel.observe_control_frame(
        face_detected=True,
        mouth_open_recognized=False,
        jaw_open=0.05,
        pitch=0.0,
        yaw=0.0,
    ) == "submit"

    wheel.hide()
    wheel.stop()
    assert [
        call for call in overlay.calls if call[0] != "raise_if_failed"
    ] == [
        ("start", None),
        ("show", ("前进一步", "后退一步", "左转", "右转")),
        ("select", 2),
        ("hide", None),
        ("stop", None),
    ]


def test_tracking_loss_and_turning_mouth_dropout_never_submit(monkeypatch):
    wheel, _, _ = _wheel(monkeypatch)
    actions = tuple(
        RobotAction(f"action_{index}", str(index), "wheel")
        for index in range(4)
    )
    wheel.update_categories(actions)

    for yaw in (0.0, 3.0, 6.0, 9.0, 11.0):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=yaw,
        ) is None
    for _ in range(20):
        assert wheel.observe_control_frame(
            face_detected=False,
            mouth_open_recognized=None,
            jaw_open=None,
            pitch=None,
            yaw=None,
        ) is None

    for _ in range(5):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=14.0,
        ) is None
    assert wheel.selected_sector is actions[2]
    for _ in range(20):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=0.0,
        ) is None


def test_tracking_loss_disarms_previously_armed_close(monkeypatch):
    wheel, _, _ = _wheel(monkeypatch)
    wheel.update_categories(tuple(str(index) for index in range(4)))
    for _ in range(5):
        wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=-14.0,
        )
    for _ in range(3):
        wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=True,
            jaw_open=0.7,
            pitch=0.0,
            yaw=0.0,
        )
    wheel.observe_control_frame(
        face_detected=False,
        mouth_open_recognized=None,
        jaw_open=None,
        pitch=None,
        yaw=None,
    )

    for _ in range(10):
        assert wheel.observe_control_frame(
            face_detected=True,
            mouth_open_recognized=False,
            jaw_open=0.05,
            pitch=0.0,
            yaw=0.0,
        ) is None


def test_fullscreen_wheel_rejects_nonfinite_head_pose(monkeypatch):
    wheel, _, _ = _wheel(monkeypatch)

    with pytest.raises(RuntimeError, match="head pose must be finite"):
        wheel.get_cardinal_from_head_pose(float("nan"), 0.0)

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
        def __init__(self, received_subject, **configuration):
            assert received_subject is subject
            assert configuration == {
                "yaw_threshold_degrees": 12.0,
                "pitch_threshold_degrees": 10.0,
            }
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
        selection="head_pose",
        yaw_threshold_degrees=12.0,
        pitch_threshold_degrees=10.0,
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
