import threading
import time
from types import SimpleNamespace

import pytest

from my_model_arch.cpu_fast import desktop
from my_model_arch.cpu_fast.eye_gaze_mouse_control import GazeMouseController


@pytest.fixture
def observer():
    state_dict = {
        "head_up": {"v": False},
        "head_down": {"v": False},
        "head_left": {"v": False},
        "head_right": {"v": False},
    }
    return SimpleNamespace(
        mouse_control=True,
        wheel=SimpleNamespace(is_hidden=True),
        head_dict=SimpleNamespace(state_dict=state_dict),
        head_angles={"yaw": 0, "pitch": 0},
        head_angles_scale={"yaw": 1, "pitch": 1},
        op_xy=(None, None),
    )


def _unlocked_controller(observer, **kwargs):
    controller = GazeMouseController(observer, **kwargs)
    controller.lock_until_time = 0
    controller.lock_with_head_until_time = 0
    return controller


def _wait_until_worker_stops(controller):
    deadline = time.monotonic() + 1
    while controller.running and time.monotonic() < deadline:
        time.sleep(0.005)
    assert not controller.running


def test_visible_cursor_uses_absolute_desktop_movement(monkeypatch, observer):
    calls = []
    monkeypatch.setattr(
        desktop,
        "move_pointer",
        lambda x, y, relative=False: calls.append((x, y, relative)),
    )
    controller = _unlocked_controller(
        observer,
        screen_width=640,
        screen_height=480,
        use_head_control_mouse=False,
    )

    controller._handle_visible_cursor(321.9, -4)

    assert calls == [(321, 0, False)]


def test_hidden_cursor_uses_relative_desktop_movement(monkeypatch, observer):
    calls = []
    monkeypatch.setattr(
        desktop,
        "move_pointer",
        lambda x, y, relative=False: calls.append((x, y, relative)),
    )
    controller = _unlocked_controller(observer)
    monkeypatch.setattr(controller, "_calculate_move", lambda x, y: (3.9, -4.2))

    controller._handle_invisible_cursor(100, 100)

    assert calls == [(3, -4, True)]


def test_visible_cursor_head_movement_uses_current_pointer(
    monkeypatch, observer
):
    calls = []
    observer.head_dict.state_dict["head_up"]["v"] = True
    observer.head_dict.state_dict["head_right"]["v"] = True
    observer.head_angles = {"yaw": 4, "pitch": 5}
    observer.head_angles_scale = {"yaw": 1, "pitch": 2}
    monkeypatch.setattr(desktop, "get_pointer_position", lambda: (100, 200))
    monkeypatch.setattr(
        desktop,
        "move_pointer",
        lambda x, y, relative=False: calls.append((x, y, relative)),
    )
    controller = _unlocked_controller(
        observer,
        screen_width=640,
        screen_height=480,
        head_coef=10,
    )

    controller._handle_visible_cursor(300, 200)

    assert calls == [(130, 230, False)]


def test_controller_rethrows_worker_failure(monkeypatch, observer):
    def fail_cursor_query():
        raise OSError("XFixes failed")

    monkeypatch.setattr(desktop, "is_cursor_visible", fail_cursor_query)
    controller = _unlocked_controller(observer)
    controller.start()
    controller.update_gaze(100, 100)
    _wait_until_worker_stops(controller)

    try:
        with pytest.raises(OSError, match="XFixes failed"):
            controller.raise_if_failed()
    finally:
        controller.stop()

    assert not any(
        thread is controller.control_thread and thread.is_alive()
        for thread in threading.enumerate()
    )
