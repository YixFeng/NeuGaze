import sys
import threading
import time
from types import SimpleNamespace

import pytest

from my_model_arch.cpu_fast import desktop
from my_model_arch.cpu_fast import eye_gaze_mouse_control as controller_module
from my_model_arch.cpu_fast.eye_gaze_mouse_control import GazeMouseController


@pytest.fixture
def observer():
    state_dict = {
        "head_up": {"v": False},
        "head_down": {"v": False},
        "head_left": {"v": False},
        "head_right": {"v": False},
    }
    observer = SimpleNamespace(
        mouse_control=True,
        wheel=SimpleNamespace(is_hidden=True),
        head_dict=SimpleNamespace(state_dict=state_dict),
        head_angles={"yaw": 0, "pitch": 0},
        head_angles_scale={"yaw": 1, "pitch": 1},
        op_xy=(None, None),
        op_xy_generation=0,
        published_op_xy_generation=0,
    )

    def next_op_xy_generation():
        observer.op_xy_generation += 1
        return observer.op_xy_generation

    def publish_op_xy(generation, x, y):
        observer.op_xy = (x, y)
        observer.published_op_xy_generation = generation

    observer.next_op_xy_generation = next_op_xy_generation
    observer.publish_op_xy = publish_op_xy
    return observer


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


def _forbid_robot_desktop_calls(monkeypatch):
    for name in (
        "get_pointer_position",
        "move_pointer",
        "key_down",
        "key_up",
        "key_up_owned",
        "scroll",
        "release_all",
        "is_cursor_visible",
    ):
        monkeypatch.setattr(
            desktop,
            name,
            lambda *args, name=name, **kwargs: pytest.fail(
                f"robot mode called desktop.{name}"
            ),
        )


@pytest.mark.parametrize(
    ("wheel_hidden", "gaze", "expected_op_xy"),
    [
        (True, (321, 123), (None, None)),
        (False, (2400, -50), (2400, -50)),
    ],
)
def test_robot_controller_only_forwards_gaze_to_visible_wheel(
    monkeypatch, observer, wheel_hidden, gaze, expected_op_xy
):
    observer.wheel.is_hidden = wheel_hidden
    controller = _unlocked_controller(
        observer, desktop_pointer_control=False
    )
    controller.running = True
    controller.update_gaze(*gaze)
    _forbid_robot_desktop_calls(monkeypatch)
    monkeypatch.setattr(
        controller_module.time,
        "sleep",
        lambda duration: setattr(controller, "running", False),
    )

    controller._control_loop()
    controller.raise_if_failed()

    assert observer.op_xy == expected_op_xy


def test_robot_controller_publishes_identical_gaze_as_fresh_samples(
    monkeypatch, observer
):
    observer.wheel.is_hidden = False
    controller = _unlocked_controller(
        observer, desktop_pointer_control=False
    )
    _forbid_robot_desktop_calls(monkeypatch)

    for _ in range(2):
        controller.running = True
        controller.update_gaze(321, 123)
        monkeypatch.setattr(
            controller_module.time,
            "sleep",
            lambda duration: setattr(controller, "running", False),
        )
        controller._control_loop()
        controller.raise_if_failed()

    assert observer.op_xy == (321, 123)
    assert observer.op_xy_generation == 2
    assert observer.published_op_xy_generation == 2


def test_desktop_wheel_selection_publishes_through_generation(
    observer,
):
    observer.wheel.is_hidden = False
    controller = _unlocked_controller(
        observer,
        select_wheel_using_head=False,
    )

    controller._handle_visible_cursor(
        observer.next_op_xy_generation(), 321, 123
    )

    assert observer.op_xy == (321, 123)
    assert observer.op_xy_generation == 1
    assert observer.published_op_xy_generation == 1


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

    controller._handle_visible_cursor(
        observer.next_op_xy_generation(), 321.9, -4
    )

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

    controller._handle_visible_cursor(
        observer.next_op_xy_generation(), 300, 200
    )

    assert calls == [(130, 230, False)]


def test_controller_rethrows_worker_failure(monkeypatch, observer):
    def fail_cursor_query():
        raise OSError("XFixes failed")

    monkeypatch.setattr(desktop, "is_cursor_visible", fail_cursor_query)
    controller = _unlocked_controller(observer)
    controller.start()
    controller.update_gaze(100, 100)
    _wait_until_worker_stops(controller)

    with pytest.raises(OSError, match="XFixes failed") as caught:
        controller.raise_if_failed()

    with pytest.raises(OSError) as stopped:
        controller.stop()

    assert stopped.value is caught.value
    assert not any(
        thread is controller.control_thread and thread.is_alive()
        for thread in threading.enumerate()
    )


def test_stop_rethrows_failure_recorded_during_join(observer):
    controller = _unlocked_controller(observer)
    source_error = OSError("late XFixes failure")
    try:
        raise source_error
    except OSError:
        source_info = sys.exc_info()

    class LateFailureThread:
        def join(self):
            controller._worker_error = source_info

    controller.running = True
    controller.control_thread = LateFailureThread()
    controller.update_gaze(100, 200)

    with pytest.raises(OSError) as caught:
        controller.stop()

    assert caught.value is source_error
    assert controller.gaze_queue.empty()
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert source_info[2] in traceback_chain


def test_stop_drains_pending_gaze(observer):
    controller = _unlocked_controller(observer)
    controller.update_gaze(100, 200)
    controller.update_gaze(300, 400)

    controller.stop()

    assert controller.gaze_queue.empty()


def test_controller_restarts_after_normal_stop(monkeypatch, observer):
    workers = []

    class Worker:
        def __init__(self, target):
            self.target = target
            self.started = False
            self.joined = False
            workers.append(self)

        def start(self):
            self.started = True

        def join(self):
            self.joined = True

    monkeypatch.setattr(controller_module.threading, "Thread", Worker)
    controller = _unlocked_controller(observer)

    controller.start()
    controller.stop()
    controller.start()

    assert len(workers) == 2
    assert workers[0].joined is True
    assert workers[1].started is True

    controller.stop()


def test_controller_does_not_restart_after_stored_error(
    monkeypatch, observer
):
    controller = _unlocked_controller(observer)
    source_error = OSError("stored worker failure")
    try:
        raise source_error
    except OSError:
        controller._worker_error = sys.exc_info()
    monkeypatch.setattr(
        controller_module.threading,
        "Thread",
        lambda **kwargs: pytest.fail("failed controller must not restart"),
    )

    with pytest.raises(OSError) as caught:
        controller.start()

    assert caught.value is source_error
    assert controller.running is False
