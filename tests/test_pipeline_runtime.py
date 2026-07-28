import builtins
import inspect
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from my_model_arch.cpu_fast import desktop
from my_model_arch.cpu_fast.camera import CameraConfig
from my_model_arch.cpu_fast import cardinal_overlay_x11 as cardinal_module
from my_model_arch.cpu_fast import eye_gaze_mouse_control as controller_module
from my_model_arch.cpu_fast import pipeline as pipeline_module
from my_model_arch.cpu_fast.keyboard_utils import Action, OpType
from my_model_arch.cpu_fast.cardinal_overlay_x11 import FullscreenCardinalWheel
from my_model_arch.cpu_fast.robot_actions import RobotAction
from my_model_arch.cpu_fast.pipeline import (
    BindKeys,
    IntegratedRegressionMediaPipeline,
    ObserverWithSectorWheel,
    RealAction,
    SectorWheel,
)


def _pipeline_without_constructor():
    pipeline = object.__new__(IntegratedRegressionMediaPipeline)
    pipeline._lifecycle_lock = threading.RLock()
    pipeline.evaluation_stop_requested = False
    pipeline.uses_desktop_input = True
    return pipeline


def _real_action_without_constructor():
    pipeline = object.__new__(RealAction)
    pipeline._lifecycle_lock = threading.RLock()
    pipeline.evaluation_stop_requested = False
    pipeline.gaze_overlay = None
    pipeline.action_output = "desktop"
    pipeline.uses_desktop_input = True
    return pipeline



def test_constructor_builds_camera_config_once(monkeypatch):
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_regression_model",
        lambda self: setattr(self, "regression_model", None),
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "load_model_from_weights",
        lambda self: None,
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_mediapipe",
        lambda self: object(),
    )

    pipeline = IntegratedRegressionMediaPipeline(
        weights="unused.param",
        device="cpu",
        cam_id=3,
        camera_backend={"linux": "opencv", "win32": "opencv"},
        camera_width=1280,
        camera_height=720,
        camera_fps=30,
    )

    assert pipeline.camera_config == CameraConfig(
        backend="opencv",
        device_id=3,
        width=1280,
        height=720,
        fps=30,
    )
    assert pipeline.camera is None


@pytest.mark.parametrize("show_gaze", [False, True])
def test_real_action_requires_gaze_config_without_importing_win32(
    monkeypatch, show_gaze
):
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_regression_model",
        lambda self: setattr(self, "regression_model", None),
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "load_model_from_weights",
        lambda self: None,
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_mediapipe",
        lambda self: object(),
    )
    monkeypatch.setattr(
        pipeline_module,
        "ExpressionEvaluator",
        lambda config: object(),
    )

    class InertThread:
        def __init__(self, target, daemon=None):
            self.target = target
            self.daemon = daemon

        def start(self):
            pass

    monkeypatch.setattr(pipeline_module.threading, "Thread", InertThread)
    requested_modules = []
    real_import = builtins.__import__

    def reject_platform_specific_import(
        name, globals=None, locals=None, fromlist=(), level=0
    ):
        if name.endswith("gaze_show_utils") or name.startswith("win32"):
            requested_modules.append(name)
            raise AssertionError(f"unexpected platform import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_platform_specific_import)

    with pytest.raises(ValueError, match="gaze_config is required"):
        RealAction(
            show_gaze=show_gaze,
            gaze_config=None,
            mouse_control_config={},
            wheel_config={},
            configuration={"type": {}},
            expression_evaluator_config={},
            weights="unused.param",
            device="cpu",
            camera_backend={"linux": "opencv", "win32": "opencv"},
            camera_width=640,
            camera_height=480,
            camera_fps=30,
            screen_size=(1920, 1080),
        )

    assert requested_modules == []


def test_start_service_opens_configured_camera_once(monkeypatch):
    source = object()
    opened = []
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.camera = None
    pipeline.camera_config = CameraConfig("opencv", 2, 640, 480, 30)
    monkeypatch.setattr(
        desktop,
        "initialize",
        lambda: pytest.fail("pipeline must not own desktop initialization"),
    )
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (1920, 1080))
    monkeypatch.setattr(
        pipeline_module,
        "open_camera",
        lambda config, platform: opened.append((config, platform)) or source,
    )

    pipeline.start_service()

    assert opened == [(pipeline.camera_config, sys.platform)]
    assert pipeline.camera is source
    assert pipeline.screen_size == (1920, 1080)
    assert pipeline.mid_point == (960, 540)


def test_setup_window_maps_first_frame_before_requesting_fullscreen(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.window_name = "track"
    pipeline.screen_size = (1280, 720)
    pipeline.open_windows = []
    events = []

    monkeypatch.setattr(
        pipeline_module.cv2,
        "namedWindow",
        lambda name, flags: events.append(("named", name, flags)),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "imshow",
        lambda name, frame: events.append(
            ("show", name, frame.shape, frame.dtype)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "waitKey",
        lambda delay: events.append(("wait", delay)) or -1,
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "moveWindow",
        lambda name, x, y: events.append(("move", name, x, y)),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "setWindowProperty",
        lambda name, prop, value: events.append(
            ("fullscreen", name, prop, value)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "getWindowProperty",
        lambda name, prop: events.append(("property", name, prop))
        or pipeline_module.cv2.WINDOW_FULLSCREEN,
    )

    pipeline.setup_window()

    assert events == [
        ("named", "track", pipeline_module.cv2.WINDOW_NORMAL),
        ("show", "track", (720, 1280, 3), pipeline_module.np.dtype("uint8")),
        ("wait", 1),
        ("move", "track", 0, 0),
        ("wait", 100),
        (
            "fullscreen",
            "track",
            pipeline_module.cv2.WND_PROP_FULLSCREEN,
            pipeline_module.cv2.WINDOW_FULLSCREEN,
        ),
        ("wait", 100),
        (
            "property",
            "track",
            pipeline_module.cv2.WND_PROP_FULLSCREEN,
        ),
    ]
    assert pipeline.open_windows == ["track"]


def test_setup_window_rejects_ignored_fullscreen_request(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.window_name = "track"
    pipeline.screen_size = (1280, 720)
    pipeline.open_windows = []
    monkeypatch.setattr(pipeline_module.cv2, "namedWindow", lambda *args: None)
    monkeypatch.setattr(pipeline_module.cv2, "imshow", lambda *args: None)
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: -1)
    monkeypatch.setattr(
        pipeline_module.cv2,
        "moveWindow",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        pipeline_module.cv2, "setWindowProperty", lambda *args: None
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "getWindowProperty",
        lambda *args: pipeline_module.cv2.WINDOW_NORMAL,
    )

    with pytest.raises(RuntimeError, match="did not enter fullscreen"):
        pipeline.setup_window()

    assert pipeline.open_windows == []


def test_cap_read_img_updates_strictly_increasing_mediapipe_timestamp(
    monkeypatch,
):
    frames = [object(), object()]
    pipeline = _pipeline_without_constructor()
    pipeline.camera = SimpleNamespace(read=lambda: frames.pop(0))
    pipeline.milliseconds_list = []
    timestamps_ns = iter([1_000_000, 3_000_000])
    monkeypatch.setattr(
        pipeline_module.time,
        "monotonic_ns",
        lambda: next(timestamps_ns),
    )

    pipeline.cap_read_img()
    first_frame = pipeline.frame
    first_timestamp = pipeline.milliseconds
    pipeline.cap_read_img()

    assert first_frame is not pipeline.frame
    assert first_timestamp == 1
    assert pipeline.milliseconds == 3
    assert pipeline.milliseconds_list == [1, 3]


def test_cap_read_img_advances_timestamp_for_frames_in_same_millisecond(
    monkeypatch,
):
    pipeline = _pipeline_without_constructor()
    pipeline.camera = SimpleNamespace(read=lambda: object())
    pipeline.milliseconds_list = []
    monkeypatch.setattr(
        pipeline_module.time,
        "monotonic_ns",
        lambda: 5_000_000,
    )

    for _ in range(3):
        pipeline.cap_read_img()

    assert pipeline.milliseconds == 7
    assert pipeline.milliseconds_list == [5, 6, 7]


def test_camera_read_exception_propagates():
    pipeline = _pipeline_without_constructor()

    class FailingCamera:
        def read(self):
            raise RuntimeError("camera disconnected")

    pipeline.camera = FailingCamera()

    with pytest.raises(RuntimeError, match="camera disconnected"):
        pipeline.cap_read_img()


def test_capture_results_uses_only_pipeline_camera():
    parameters = inspect.signature(
        IntegratedRegressionMediaPipeline.get_results_from_capture
    ).parameters

    assert list(parameters) == ["self"]


def test_quit_closes_camera_and_releases_desktop(monkeypatch):
    calls = []
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = SimpleNamespace(close=lambda: calls.append("camera"))
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: calls.append("controller")
    )
    pipeline.destroy_window = lambda: calls.append("windows")
    monkeypatch.setattr(
        desktop, "release_all", lambda: calls.append("release_all")
    )
    monkeypatch.setattr(
        desktop,
        "close",
        lambda: pytest.fail("pipeline must not close application desktop"),
    )

    pipeline.quit_pipeline()

    assert pipeline.quit is True
    assert pipeline.end_calibration_signal is True
    assert "release_all" in calls
    assert "controller" in calls
    assert "camera" in calls
    assert "windows" in calls
    assert pipeline.camera is None


def test_quit_attempts_every_cleanup_and_aggregates_failures(monkeypatch):
    calls = []

    def fail(name):
        calls.append(name)
        raise RuntimeError(name)

    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = SimpleNamespace(close=lambda: fail("camera"))
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: fail("controller")
    )
    pipeline.destroy_window = lambda: fail("windows")
    monkeypatch.setattr(desktop, "release_all", lambda: fail("release_all"))
    monkeypatch.setattr(
        desktop,
        "close",
        lambda: pytest.fail("pipeline must not close application desktop"),
    )

    with pytest.raises(ExceptionGroup) as caught:
        pipeline.quit_pipeline()

    assert calls == ["release_all", "controller", "camera", "windows"]
    assert [str(error) for error in caught.value.exceptions] == calls


def test_quit_preserves_primary_error_and_exposes_cleanup_failures(monkeypatch):
    calls = []

    def fail(name):
        calls.append(name)
        raise RuntimeError(name)

    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = SimpleNamespace(close=lambda: fail("camera"))
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: fail("controller")
    )
    pipeline.destroy_window = lambda: fail("windows")
    monkeypatch.setattr(desktop, "release_all", lambda: fail("release_all"))
    monkeypatch.setattr(
        desktop,
        "close",
        lambda: pytest.fail("pipeline must not close application desktop"),
    )
    try:
        raise ValueError("primary")
    except ValueError as error:
        primary_error = error
        primary_traceback = error.__traceback__

    with pytest.raises(ValueError) as caught:
        pipeline.quit_pipeline(primary_error)

    assert caught.value is primary_error
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert primary_traceback in traceback_chain
    assert calls == ["release_all", "controller", "camera", "windows"]
    assert len(caught.value.__notes__) == 4
    for name, note in zip(calls, caught.value.__notes__):
        assert name in note
        assert "RuntimeError" in note


def test_quit_preserves_primary_when_cleanup_raises_base_exception(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.destroy_window = lambda: None
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: (_ for _ in ()).throw(SystemExit("cleanup exit")),
    )
    primary_error = ValueError("primary")

    with pytest.raises(ValueError) as caught:
        pipeline.quit_pipeline(primary_error)

    assert caught.value is primary_error
    assert any(
        "desktop.release_all" in note and "SystemExit" in note
        for note in caught.value.__notes__
    )


def test_quit_groups_cleanup_base_exceptions_and_attempts_all(monkeypatch):
    calls = []
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None

    def fail(name, error):
        calls.append(name)
        raise error

    pipeline.destroy_window = lambda: fail(
        "windows", KeyboardInterrupt("window cleanup")
    )
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: fail("release_all", SystemExit("desktop cleanup")),
    )

    with pytest.raises(BaseExceptionGroup) as caught:
        pipeline.quit_pipeline()

    assert calls == ["release_all", "windows"]
    assert [type(error) for error in caught.value.exceptions] == [
        SystemExit,
        KeyboardInterrupt,
    ]


def test_quit_stops_wheel_before_releasing_desktop(monkeypatch):
    calls = []

    class Wheel:
        def stop(self):
            calls.append("wheel.stop")

    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.wheel = Wheel()
    pipeline.destroy_window = lambda: calls.append("windows")
    monkeypatch.setattr(
        desktop, "release_all", lambda: calls.append("desktop.release_all")
    )

    pipeline.quit_pipeline()

    assert calls.index("wheel.stop") < calls.index(
        "desktop.release_all"
    )


def test_screen_resolution_comes_from_desktop(monkeypatch):
    pipeline = _pipeline_without_constructor()
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (2560, 1440))

    assert pipeline.get_screen_resolution() == (2560, 1440)


def test_bind_keys_queries_pointer_through_desktop(monkeypatch):
    pipeline = object.__new__(BindKeys)
    pipeline.predicted_position = (300, 250)
    monkeypatch.setattr(desktop, "get_pointer_position", lambda: (100, 50))

    pipeline.move_mouse()

    assert pipeline.mouse_dict == {
        "rel_x": 200,
        "rel_y": 200,
        "x": 300,
        "y": 250,
        "mx": 100,
        "my": 50,
    }


def test_sector_wheel_centers_pointer_through_desktop(monkeypatch):
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel.lock = threading.Lock()
    wheel.current_categories = None
    wheel.selected_sector = None
    wheel.is_hidden = True
    wheel.sector_wheel = SimpleNamespace(
        update_categories=lambda *args, **kwargs: None
    )
    wheel.subject = SimpleNamespace(
        keys_dict=SimpleNamespace(state_dict={"open": {"v": True}}),
        wheel_categories=["a"],
        key_keeps_wheel_opening="open",
        mid_point=(960, 540),
        wheel_layout_type="circle",
        action_output="desktop",
        quit=False,
    )
    calls = []

    def move_pointer(x, y, relative=False):
        calls.append((x, y, relative))
        wheel.should_run = False

    monkeypatch.setattr(pipeline_module.time, "sleep", lambda duration: None)
    monkeypatch.setattr(desktop, "move_pointer", move_pointer)

    wheel.sector_wheel_main_loop()

    assert calls == [(960, 540, False)]


def _cardinal_wheel_without_tk(radius):
    wheel = object.__new__(SectorWheel)
    wheel.radius = radius
    wheel.canvas = SimpleNamespace(
        winfo_width=lambda: 2 * radius,
        winfo_height=lambda: 2 * radius,
    )
    return wheel


@pytest.mark.parametrize(
    ("point", "expected_index"),
    [
        ((400, 100), 0),
        ((400, 700), 1),
        ((100, 400), 2),
        ((700, 400), 3),
        ((0, 0), None),
    ],
)
def test_cardinal_wheel_maps_fixed_directions(point, expected_index):
    wheel = _cardinal_wheel_without_tk(radius=400)
    event = SimpleNamespace(x=point[0], y=point[1])

    assert wheel.get_cardinal_from_mouse_position(event) == expected_index


@pytest.mark.parametrize(
    ("point", "expected_index"),
    [
        ((600, 200), 0),
        ((200, 600), 1),
        ((400, 400), None),
    ],
)
def test_cardinal_wheel_uses_vertical_axis_for_ties_and_none_at_center(
    point, expected_index
):
    wheel = _cardinal_wheel_without_tk(radius=400)
    event = SimpleNamespace(x=point[0], y=point[1])

    assert wheel.get_cardinal_from_mouse_position(event) == expected_index


def test_pipeline_import_graph_is_platform_neutral_in_fresh_interpreter():
    repository_root = Path(__file__).resolve().parents[1]
    source = """
import builtins
import sys

real_import = builtins.__import__
forbidden = {
    "keyboard",
    "pyautogui",
    "win32api",
    "win32con",
    "my_model_arch.cpu_fast.desktop.win32",
    "my_model_arch.cpu_fast.gaze_show_utils",
}

def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in forbidden or any(name.endswith("." + item) for item in forbidden):
        raise AssertionError(f"platform-specific import: {name}")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = guarded_import
import my_model_arch.cpu_fast.pipeline
assert not (forbidden & set(sys.modules))
"""
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def _run_one_action(pipeline, action):
    pipeline.sys_mode_list = []
    pipeline.action_queue = queue.Queue()
    pipeline.wheel = SimpleNamespace(stop=lambda: None)
    pipeline._execute_action(action)


def test_supported_action_executes_synchronously(monkeypatch):
    pipeline = _real_action_without_constructor()
    caller_thread = threading.get_ident()
    executed_on = []
    action = SimpleNamespace(
        keyname="w",
        execute=lambda: executed_on.append(threading.get_ident()),
    )
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)

    _run_one_action(pipeline, action)

    assert executed_on == [caller_thread]


@pytest.mark.parametrize(
    "key", ["w", "ctrl+a", "type", "scroll_up"]
)
def test_real_action_none_never_routes_input_or_changes_mode(
    monkeypatch, key
):
    pipeline = _real_action_without_constructor()
    pipeline.sys_mode = "game"
    pipeline.sys_mode_list = ["type"]
    pipeline.last_scroll_time = 0
    pipeline.scroll_throttle_interval = 0
    pipeline.head_angles = {"roll": 10}
    pipeline.head_angles_scale = {"roll": 8}
    pipeline.scroll_coef = 2
    calls = []
    monkeypatch.setattr(desktop, "supports_key", lambda value: value == "w")
    monkeypatch.setattr(desktop, "key_down", lambda value: calls.append(("down", value)))
    monkeypatch.setattr(desktop, "key_up", lambda value: calls.append(("up", value)))
    monkeypatch.setattr(desktop, "scroll", lambda value: calls.append(("scroll", value)))

    pipeline._execute_action_once(Action(key, OpType.NONE))

    assert calls == []
    assert pipeline.sys_mode == "game"
    assert pipeline.last_scroll_time == 0



def test_hotkey_uses_explicit_down_and_reverse_up(monkeypatch):
    pipeline = _real_action_without_constructor()
    calls = []
    action = Action("ctrl+a", OpType.KEYPRESS)
    monkeypatch.setattr(desktop, "supports_key", lambda key: False)
    monkeypatch.setattr(
        desktop, "key_down", lambda key: calls.append(("down", key))
    )
    monkeypatch.setattr(
        desktop, "key_up", lambda key: calls.append(("up", key))
    )

    _run_one_action(pipeline, action)

    assert calls == [
        ("down", "ctrl"),
        ("down", "a"),
        ("up", "a"),
        ("up", "ctrl"),
    ]


def test_hotkey_keydown_failure_releases_pressed_keys_and_preserves_primary(
    monkeypatch,
):
    pipeline = _real_action_without_constructor()
    calls = []
    primary_error = OSError("shift down failed")
    release_error = RuntimeError("ctrl release failed")

    def key_down(key):
        calls.append(("down", key))
        if key == "shift":
            raise primary_error

    def key_up(key):
        calls.append(("up", key))
        raise release_error

    monkeypatch.setattr(desktop, "supports_key", lambda key: False)
    monkeypatch.setattr(desktop, "key_down", key_down)
    monkeypatch.setattr(desktop, "key_up", key_up)

    with pytest.raises(OSError) as caught:
        _run_one_action(pipeline, Action("ctrl+shift+a", OpType.KEYPRESS))

    assert caught.value is primary_error
    assert calls == [
        ("down", "ctrl"),
        ("down", "shift"),
        ("up", "ctrl"),
    ]
    assert caught.value.__notes__ == [
        "desktop.key_up('ctrl') failed with "
        "RuntimeError: ctrl release failed"
    ]


def test_hotkey_multiple_keyup_failures_are_aggregated(monkeypatch):
    pipeline = _real_action_without_constructor()
    release_errors = {
        "a": RuntimeError("a release failed"),
        "ctrl": OSError("ctrl release failed"),
    }
    calls = []

    monkeypatch.setattr(desktop, "supports_key", lambda key: False)
    monkeypatch.setattr(
        desktop,
        "key_down",
        lambda key: calls.append(("down", key)),
    )

    def key_up(key):
        calls.append(("up", key))
        raise release_errors[key]

    monkeypatch.setattr(desktop, "key_up", key_up)

    with pytest.raises(ExceptionGroup) as caught:
        _run_one_action(pipeline, Action("ctrl+a", OpType.KEYPRESS))

    assert calls == [
        ("down", "ctrl"),
        ("down", "a"),
        ("up", "a"),
        ("up", "ctrl"),
    ]
    assert caught.value.exceptions == (
        release_errors["a"],
        release_errors["ctrl"],
    )


def test_scroll_uses_desktop_synchronously(monkeypatch):
    pipeline = _real_action_without_constructor()
    pipeline.last_scroll_time = 0
    pipeline.scroll_throttle_interval = 0
    pipeline.head_angles = {"roll": 10}
    pipeline.head_angles_scale = {"roll": 8}
    pipeline.scroll_coef = 2
    calls = []
    monkeypatch.setattr(desktop, "supports_key", lambda key: False)
    monkeypatch.setattr(desktop, "scroll", calls.append)

    _run_one_action(pipeline, Action("scroll_up", OpType.KEYPRESS))

    assert calls == [4]


def test_calibration_quit_hotkey_uses_desktop(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.screen_size = (640, 480)
    pipeline.every_point_has_n_images = 1
    pipeline.images_freq = 1
    pipeline.quit = False
    pipeline.shrink_point = lambda *args: None
    calls = []
    monkeypatch.setattr(
        desktop,
        "are_keys_down",
        lambda keys: calls.append(keys) or True,
    )

    result = pipeline.calibrate_single_point_dynamic(
        object(), (100, 100), 0, 1, "unused/"
    )

    assert result == []
    assert pipeline.quit is True
    assert calls == [("esc", "q")]


def test_calibration_capture_error_propagates(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.screen_size = (640, 480)
    pipeline.every_point_has_n_images = 1
    pipeline.images_freq = 1
    pipeline.quit = False
    pipeline.shrink_point = lambda *args: None
    pipeline.check_eyes_closed = lambda: False
    source_error = RuntimeError("camera disconnected")
    hotkey_checks = []

    def are_keys_down(keys):
        hotkey_checks.append(keys)
        return len(hotkey_checks) > 1

    monkeypatch.setattr(desktop, "are_keys_down", are_keys_down)
    pipeline.get_results_from_capture = lambda: (_ for _ in ()).throw(
        source_error
    )

    with pytest.raises(RuntimeError) as caught:
        pipeline.calibrate_single_point_dynamic(
            object(), (100, 100), 0, 1, "unused/"
        )

    assert caught.value is source_error
    assert hotkey_checks == [("esc", "q")]


def _configure_public_run(pipeline, camera, fail=None):
    pipeline.camera = camera
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.is_calibrating = True
    pipeline.start_with_calibration = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.setup_window = lambda: None
    pipeline.destroy_window = lambda: None
    pipeline.call_before_while_loop = lambda: None
    pipeline.call_after_each_eval_loop = lambda: None
    pipeline.call_after_while_loop = lambda: None

    if fail is None:
        pipeline.calibrate = lambda *args, **kwargs: None

        def evaluate(*args, **kwargs):
            pipeline.end_calibration_signal = True

        pipeline.evaluate = evaluate
    else:
        pipeline.calibrate = fail
        pipeline.evaluate = fail


@pytest.mark.parametrize(
    "entrypoint", ["start_calibration", "start_evaluation"]
)
def test_public_run_closes_only_per_run_resources_on_normal_completion(
    monkeypatch, entrypoint
):
    calls = []
    camera = SimpleNamespace(close=lambda: calls.append("camera.close"))
    pipeline = _pipeline_without_constructor()
    _configure_public_run(pipeline, camera)
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: calls.append("controller.stop")
    )
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "are_keys_down", lambda keys: True)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: calls.append("desktop.release_all"),
    )

    getattr(pipeline, entrypoint)()

    assert calls == ["controller.stop", "camera.close"]
    assert pipeline.camera is None
    assert pipeline.quit is False


def test_start_calibration_does_not_turn_failed_calibration_into_success(
    monkeypatch
):
    camera = SimpleNamespace(close=lambda: None)
    pipeline = _pipeline_without_constructor()
    _configure_public_run(pipeline, camera)
    pipeline.calibrate = lambda camera: None
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)

    assert pipeline.start_calibration() is None


@pytest.mark.parametrize("failure_stage", ["validation", "training", "save"])
def test_finish_calibration_preserves_production_failure(
    failure_stage
):
    pipeline = _pipeline_without_constructor()
    pipeline.data_list = [{"sample": "current calibration"}]
    pipeline.generate_quality_report = lambda path: None
    pipeline.save_calibration_data = lambda path: None
    pipeline.use_accumulated_training = False
    pipeline.calibrate_num_points = 1
    pipeline.every_point_has_n_images = 1
    pipeline.validate_training_data = lambda: True
    pipeline.train_regression = lambda reset: None
    pipeline.is_model_fitted = lambda: True
    pipeline.save_model = lambda: None
    pipeline.show_calibration_success = lambda: None
    pipeline.show_calibration_failure = lambda message: None
    error = RuntimeError(f"{failure_stage} failed")

    if failure_stage == "validation":
        pipeline.validate_training_data = lambda: (_ for _ in ()).throw(error)
    elif failure_stage == "training":
        pipeline.train_regression = lambda reset: (_ for _ in ()).throw(error)
    else:
        pipeline.save_model = lambda: (_ for _ in ()).throw(error)

    with pytest.raises(RuntimeError) as caught:
        pipeline.finish_calibration("calibration/current", False, None, None)

    assert caught.value is error


def test_finish_calibration_trains_and_saves_production_model(
    tmp_path, monkeypatch
):
    pipeline = _pipeline_without_constructor()
    pipeline.screen_size = (4096, 2160)
    pipeline.calibrate_num_points = 9
    pipeline.every_point_has_n_images = 25
    pipeline.images_freq = 15
    pipeline.eye_blink_threshold = 0.5
    pipeline.use_accumulated_training = True
    pipeline.max_accumulated_datasets = 10
    pipeline.calibration_time = "20260728_150000"
    pipeline.regression_model_type = "lassocv"
    pipeline.regression_model = pipeline_module.MultiTaskLassoCV()
    pipeline.collect_historical_calibration_data = lambda: []
    pipeline.show_calibration_success = lambda: None
    pipeline.show_calibration_failure = lambda message: pytest.fail(message)
    pipeline.data_list = []

    for point_index in range(9):
        label = (
            (point_index % 3 + 1) * 1024,
            (point_index // 3 + 1) * 540,
        )
        for sample_index in range(25):
            signal = point_index + sample_index / 100
            landmarks = pipeline_module.np.zeros((478, 3))
            landmarks[:, 2] = signal
            pipeline.data_list.append(
                {
                    "box": [signal, signal + 1, signal + 2, signal + 3],
                    "mediapipe_results": landmarks.tolist(),
                    "yaw": signal,
                    "pitch": -signal,
                    "label": label,
                    "target_point": label,
                    "quality_score": 0.8,
                    "image_path": f"images/{point_index}_{sample_index}.png",
                }
            )

    monkeypatch.chdir(tmp_path)
    calibration_path = (
        tmp_path / "calibration" / pipeline.calibration_time
    )

    assert pipeline.finish_calibration(
        f"{calibration_path}/",
        False,
        None,
        None,
    ) is True
    assert (calibration_path / "quality_report.json").is_file()
    assert (calibration_path / "train_data.jsonl").is_file()
    assert (
        tmp_path
        / "model_weights"
        / pipeline.calibration_time
        / "model.pkl"
    ).is_file()
    assert pipeline.is_model_fitted() is True


def test_accumulated_training_preserves_training_failure(tmp_path):
    data_path = tmp_path / "train_data.jsonl"
    data_path.write_text('{"label":[1,2]}\n', encoding="utf-8")
    pipeline = _pipeline_without_constructor()
    pipeline.collect_historical_calibration_data = lambda: [str(data_path)]
    error = RuntimeError("accumulated regression failed")
    pipeline.train_regression = lambda **kwargs: (_ for _ in ()).throw(error)

    with pytest.raises(RuntimeError) as caught:
        pipeline.train_with_accumulated_data()

    assert caught.value is error


def test_accumulated_training_preserves_invalid_dataset_error(tmp_path):
    data_path = tmp_path / "train_data.jsonl"
    data_path.write_text("not json\n", encoding="utf-8")
    pipeline = _pipeline_without_constructor()
    pipeline.collect_historical_calibration_data = lambda: [str(data_path)]

    with pytest.raises(pipeline_module.jsonlines.InvalidLineError) as caught:
        pipeline.train_with_accumulated_data()

    assert caught.value.lineno == 1
    assert caught.value.line == "not json"


@pytest.mark.parametrize(
    "entrypoint,cancellation",
    [
        ("start_calibration", "calibrate"),
        ("demo", "nested_calibrate"),
        ("demo", "quit_hotkey"),
    ],
)
def test_public_cancellation_uses_terminal_cleanup(
    monkeypatch, entrypoint, cancellation
):
    calls = []
    camera = SimpleNamespace(close=lambda: calls.append("camera.close"))
    pipeline = _pipeline_without_constructor()
    _configure_public_run(pipeline, camera)
    pipeline.start_with_calibration = cancellation == "nested_calibrate"
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: calls.append("controller.stop")
    )
    pipeline.destroy_window = lambda: calls.append("windows")

    class Wheel:
        def stop(self):
            assert pipeline.quit is True
            calls.append("wheel.stop")

    pipeline.wheel = Wheel()


    def cancel_calibration(*args, **kwargs):
        pipeline.quit = True

    if cancellation in ("calibrate", "nested_calibrate"):
        pipeline.calibrate = cancel_calibration

    hotkey_calls = []

    def are_keys_down(keys):
        hotkey_calls.append(keys)
        return cancellation in ("nested_calibrate", "quit_hotkey")

    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "are_keys_down", are_keys_down)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: calls.append("desktop.release_all"),
    )

    result = getattr(pipeline, entrypoint)()

    assert result is None
    assert calls == [
        "wheel.stop",
        "desktop.release_all",
        "controller.stop",
        "camera.close",
        "windows",
    ]
    assert pipeline.quit is True
    assert pipeline.camera is None
    if cancellation == "nested_calibrate":
        assert hotkey_calls == []
    elif cancellation == "quit_hotkey":
        assert hotkey_calls == [("esc", "q")]


@pytest.mark.parametrize(
    "entrypoint", ["start_calibration", "start_evaluation", "demo"]
)
def test_public_run_error_closes_camera_and_preserves_identity_and_traceback(
    monkeypatch, entrypoint
):
    close_calls = []
    camera = SimpleNamespace(close=lambda: close_calls.append("camera.close"))
    pipeline = _pipeline_without_constructor()
    source_error = RuntimeError(f"{entrypoint} failed")
    source_traceback = []

    def fail(*args, **kwargs):
        try:
            raise source_error
        except RuntimeError as error:
            source_traceback.append(error.__traceback__)
            raise

    _configure_public_run(pipeline, camera, fail)
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "are_keys_down", lambda keys: False)
    monkeypatch.setattr(desktop, "release_all", lambda: None)

    with pytest.raises(RuntimeError) as caught:
        getattr(pipeline, entrypoint)()

    assert caught.value is source_error
    assert close_calls == ["camera.close"]
    assert pipeline.camera is None
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert source_traceback[0] in traceback_chain


def test_each_evaluation_iteration_checks_controller_failure(monkeypatch):
    pipeline = _real_action_without_constructor()
    calls = []
    pipeline.decode = lambda: calls.append("decode")
    pipeline.mouse_dict = None
    pipeline.quit = False
    pipeline.wheel = SimpleNamespace(
        raise_if_failed=lambda: calls.append("wheel.raise_if_failed")
    )
    pipeline.gaze_mouse_controller = SimpleNamespace(
        raise_if_failed=lambda: calls.append("raise_if_failed"),
    )
    pipeline._drain_actions = lambda: calls.append("drain_actions")
    monkeypatch.setattr(
        BindKeys,
        "call_after_each_eval_loop",
        lambda self: calls.append("inherited"),
    )

    pipeline.call_after_each_eval_loop()

    assert calls == [
        "wheel.raise_if_failed",
        "raise_if_failed",
        "inherited",
        "decode",
        "drain_actions",
    ]


def _initialize_redesigned_lifecycle(pipeline):
    pipeline._lifecycle_lock = threading.RLock()
    pipeline.action_queue = queue.Queue()
    pipeline.gaze_running = False
    pipeline.gaze_thread = None
    pipeline.gaze_overlay = None


class _CleanupHandoffRLock:
    """Hand an armed outer release to a waiting cleanup thread."""

    def __init__(self):
        self._lock = threading.RLock()
        self._depth = threading.local()
        self.cleanup_thread_id = None
        self.cleanup_enter_attempted = threading.Event()
        self.cleanup_finished = threading.Event()
        self._handoff_armed = False
        self._handoff_done = False

    def arm_handoff(self):
        self._handoff_armed = True

    def __enter__(self):
        if threading.get_ident() == self.cleanup_thread_id:
            self.cleanup_enter_attempted.set()
        self._lock.acquire()
        depth = getattr(self._depth, "value", 0)
        self._depth.value = depth + 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        depth = self._depth.value
        outermost = depth == 1
        self._depth.value = depth - 1
        handoff = (
            outermost
            and self._handoff_armed
            and not self._handoff_done
        )
        if handoff:
            self._handoff_done = True
        self._lock.release()
        if handoff:
            assert self.cleanup_finished.wait(1)


def test_evaluation_boundary_drains_every_pending_action(monkeypatch):
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.sys_mode_list = []
    caller_thread = threading.get_ident()
    executed = []
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    for label in ("first", "second", "third"):
        pipeline.action_queue.put(
            SimpleNamespace(
                keyname=label,
                execute=lambda label=label: executed.append(
                    (label, threading.get_ident())
                ),
            )
        )

    pipeline._drain_actions()

    assert executed == [
        ("first", caller_thread),
        ("second", caller_thread),
        ("third", caller_thread),
    ]
    assert pipeline.action_queue.empty()


def test_finish_stops_wheel_then_drains_final_actions_without_run_leak(
    monkeypatch,
):
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.sys_mode_list = []
    pipeline.quit = False
    pipeline.destroy_window = lambda: None
    pipeline.gaze_mouse_controller = SimpleNamespace(stop=lambda: None)
    executed = []
    run_id = 0

    class FinalActionWheel:
        def stop(self):
            pipeline.action_queue.put(
                SimpleNamespace(
                    keyname=f"run-{run_id}",
                    execute=lambda: executed.append(run_id),
                )
            )

    pipeline.wheel = FinalActionWheel()
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)

    for current_run in (1, 2):
        run_id = current_run
        pipeline.camera = SimpleNamespace(close=lambda: None)
        pipeline._finish_run()
        assert executed == list(range(1, current_run + 1))
        assert pipeline.action_queue.empty()


def test_final_action_failure_preserves_exception_object_and_traceback(
    monkeypatch,
):
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.sys_mode_list = []
    pipeline.quit = False
    pipeline.camera = None
    pipeline.destroy_window = lambda: None
    pipeline.gaze_mouse_controller = SimpleNamespace(stop=lambda: None)
    source_error = OSError("final wheel action failed")
    source_traceback = []

    def fail():
        try:
            raise source_error
        except OSError as error:
            source_traceback.append(error.__traceback__)
            raise

    class FinalActionWheel:
        def stop(self):
            pipeline.action_queue.put(
                SimpleNamespace(keyname="a", execute=fail)
            )

    pipeline.wheel = FinalActionWheel()
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)

    with pytest.raises(OSError) as caught:
        pipeline._finish_run()

    assert caught.value is source_error
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert source_traceback[0] in traceback_chain
    assert pipeline.action_queue.empty()


@pytest.mark.parametrize("failure_path", ["queued", "direct"])
def test_action_failure_stops_wheel_and_discards_post_failure_callback(
    monkeypatch,
    failure_path,
):
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.sys_mode_list = []
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.destroy_window = lambda: None
    executed = []
    source_error = OSError("first action failed")
    cleanup_error = RuntimeError("wheel stop failed after join")
    source_traceback = []

    def fail():
        try:
            raise source_error
        except OSError as error:
            source_traceback.append(error.__traceback__)
            raise

    class LateActionWheel:
        def __init__(self):
            self.stop_calls = 0

        def stop(self):
            self.stop_calls += 1
            if self.stop_calls == 1:
                pipeline.action_queue.put(
                    SimpleNamespace(
                        keyname="late",
                        execute=lambda: executed.append("late"),
                    )
                )
                raise cleanup_error

    pipeline.wheel = LateActionWheel()
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)

    failing_action = SimpleNamespace(
        keyname="failing",
        execute=fail,
    )
    if failure_path == "queued":
        pipeline.action_queue.put(failing_action)
        fail_action = pipeline._drain_actions
    else:
        fail_action = lambda: pipeline._execute_action(
            failing_action
        )

    try:
        fail_action()
    except BaseException as error:
        with pytest.raises(OSError) as caught:
            pipeline.quit_pipeline(error)

    assert caught.value is source_error
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert source_traceback[0] in traceback_chain
    assert executed == []
    assert pipeline.action_queue.empty()
    assert pipeline.wheel.stop_calls == 2
    assert any(
        "wheel.stop" in note and "wheel stop failed after join" in note
        for note in source_error.__notes__
    )



def test_request_evaluation_stop_closes_camera_without_lifecycle_lock():
    events = []
    pipeline = _pipeline_without_constructor()
    pipeline.end_calibration_signal = False
    pipeline.evaluation_stop_requested = False
    pipeline.camera = SimpleNamespace(
        close=lambda: events.append("camera.close")
    )

    pipeline.request_evaluation_stop()

    assert pipeline.evaluation_stop_requested is True
    assert pipeline.end_calibration_signal is True
    assert events == ["camera.close"]


def test_camera_error_from_explicit_evaluation_stop_uses_cancel_cleanup():
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.evaluation_stop_requested = False
    pipeline.camera = object()
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.call_before_while_loop = lambda: None
    interrupted = RuntimeError("camera read interrupted by close")
    cleanup_primary_errors = []

    def evaluate(camera):
        pipeline.evaluation_stop_requested = True
        raise interrupted

    def quit_pipeline(primary_error=None):
        cleanup_primary_errors.append(primary_error)
        pipeline.quit = True

    pipeline.evaluate = evaluate
    pipeline.quit_pipeline = quit_pipeline

    pipeline.start_evaluation()

    assert cleanup_primary_errors == [None]
    assert pipeline.quit is True


def test_run_start_racing_terminal_quit_cannot_start_resources(
    monkeypatch,
):
    pipeline = _pipeline_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.camera_config = CameraConfig("opencv", 0, 640, 480, 30)
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.destroy_window = lambda: None
    started = []
    start_errors = []
    cleanup_entered = threading.Event()
    allow_cleanup = threading.Event()
    release_count = 0

    def release_all():
        nonlocal release_count
        release_count += 1
        if release_count == 1:
            cleanup_entered.set()
            assert allow_cleanup.wait(1)

    def open_source(config, platform):
        started.append("camera")
        return SimpleNamespace(close=lambda: None)

    pipeline.call_before_while_loop = lambda: started.append("run")
    pipeline.call_after_each_eval_loop = lambda: None
    pipeline.call_after_while_loop = lambda: None
    pipeline.evaluate = lambda camera: setattr(
        pipeline, "end_calibration_signal", True
    )
    monkeypatch.setattr(desktop, "release_all", release_all)
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (640, 480))
    monkeypatch.setattr(pipeline_module, "open_camera", open_source)
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)

    quit_thread = threading.Thread(target=pipeline.quit_pipeline)
    quit_thread.start()
    assert cleanup_entered.wait(1)

    def start_run():
        try:
            pipeline.start_evaluation()
        except BaseException as error:
            start_errors.append(error)

    start_thread = threading.Thread(target=start_run)
    start_thread.start()
    allow_cleanup.set()
    quit_thread.join(1)
    start_thread.join(1)

    assert not quit_thread.is_alive()
    assert not start_thread.is_alive()
    assert started == []
    assert len(start_errors) == 1
    assert isinstance(start_errors[0], RuntimeError)
    assert str(start_errors[0]) == "pipeline has been shut down"
    assert pipeline.quit is True
    assert pipeline.camera is None


@pytest.mark.parametrize(
    "entrypoint,start_with_calibration,consumer_name",
    [
        ("start_evaluation", False, "evaluate"),
        ("start_calibration", False, "calibrate"),
        ("demo", False, "evaluate"),
        ("demo", True, "calibrate"),
    ],
)
def test_terminal_cleanup_waits_for_first_camera_consuming_boundary(
    monkeypatch,
    entrypoint,
    start_with_calibration,
    consumer_name,
):
    class Camera:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    camera = Camera()
    pipeline = _pipeline_without_constructor()
    _configure_public_run(pipeline, camera)
    lifecycle_lock = _CleanupHandoffRLock()
    pipeline._lifecycle_lock = lifecycle_lock
    pipeline.start_with_calibration = start_with_calibration
    boundary_entered = threading.Event()
    allow_boundary_return = threading.Event()

    def pause_after_authorization():
        with lifecycle_lock:
            boundary_entered.set()
            assert allow_boundary_return.wait(1)

    if entrypoint == "start_calibration":
        pipeline.setup_window = pause_after_authorization
    else:
        pipeline.call_before_while_loop = pause_after_authorization
    uses = []
    run_errors = []
    cleanup_errors = []

    def consume(camera_argument, *args, **kwargs):
        uses.append(
            (
                consumer_name,
                camera_argument,
                None if camera_argument is None else camera_argument.closed,
            )
        )
        if consumer_name == "evaluate":
            pipeline.end_calibration_signal = True

    pipeline.evaluate = consume
    pipeline.calibrate = consume
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "are_keys_down", lambda keys: False)
    monkeypatch.setattr(desktop, "release_all", lambda: None)

    def run_public_entrypoint():
        try:
            getattr(pipeline, entrypoint)()
        except BaseException as error:
            run_errors.append(error)

    def run_cleanup():
        lifecycle_lock.cleanup_thread_id = threading.get_ident()
        try:
            pipeline.quit_pipeline()
        except BaseException as error:
            cleanup_errors.append(error)
        finally:
            lifecycle_lock.cleanup_finished.set()

    run_thread = threading.Thread(target=run_public_entrypoint)
    run_thread.start()
    assert boundary_entered.wait(1)

    cleanup_thread = threading.Thread(target=run_cleanup)
    cleanup_thread.start()
    assert lifecycle_lock.cleanup_enter_attempted.wait(1)
    lifecycle_lock.arm_handoff()
    allow_boundary_return.set()
    run_thread.join(2)
    cleanup_thread.join(2)

    assert not run_thread.is_alive()
    assert not cleanup_thread.is_alive()
    assert run_errors == []
    assert cleanup_errors == []
    assert uses == []
    assert camera.closed is True
    assert pipeline.camera is None
    assert pipeline.quit is True


def test_explicit_quit_stops_demo_before_another_evaluation(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.camera = SimpleNamespace(close=lambda: None)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.start_with_calibration = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.destroy_window = lambda: None
    pipeline.call_before_while_loop = lambda: None
    pipeline.call_after_each_eval_loop = lambda: None
    pipeline.call_after_while_loop = lambda: pytest.fail(
        "terminal demo must not take the normal finish path"
    )
    evaluation_entered = threading.Event()
    allow_evaluation_return = threading.Event()
    evaluation_calls = 0
    run_errors = []
    cleanup_errors = []

    def evaluate(camera):
        nonlocal evaluation_calls
        evaluation_calls += 1
        if evaluation_calls == 1:
            evaluation_entered.set()
            assert allow_evaluation_return.wait(1)
            return
        raise AssertionError("demo evaluated after terminal cleanup")

    pipeline.evaluate = evaluate
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "are_keys_down", lambda keys: False)
    monkeypatch.setattr(desktop, "release_all", lambda: None)

    def run_demo():
        try:
            pipeline.demo()
        except BaseException as error:
            run_errors.append(error)

    def run_cleanup():
        try:
            pipeline.quit_pipeline()
        except BaseException as error:
            cleanup_errors.append(error)

    run_thread = threading.Thread(target=run_demo)
    run_thread.start()
    assert evaluation_entered.wait(1)

    cleanup_thread = threading.Thread(target=run_cleanup)
    cleanup_thread.start()
    deadline = time.monotonic() + 1
    while not pipeline.quit and time.monotonic() < deadline:
        time.sleep(0.001)
    assert pipeline.quit is True
    allow_evaluation_return.set()
    run_thread.join(2)
    cleanup_thread.join(2)

    assert not run_thread.is_alive()
    assert not cleanup_thread.is_alive()
    assert evaluation_calls == 1
    assert run_errors == []
    assert cleanup_errors == []


def test_wheel_stop_requests_tk_destroy_and_joins_stored_thread(
    monkeypatch,
):
    roots = []
    mainloop_started = threading.Event()

    class FakeRoot:
        def __init__(self):
            self.destroyed = threading.Event()
            self.after_calls = []
            roots.append(self)

        def withdraw(self):
            pass

        def after(self, delay, callback):
            self.after_calls.append((delay, callback))
            if delay == 0:
                callback()

        def mainloop(self):
            mainloop_started.set()
            assert self.destroyed.wait(1)

        def destroy(self):
            self.destroyed.set()

    class FakeToplevel:
        def __init__(self, root):
            self.root = root

        def overrideredirect(self, enabled):
            pass

        def attributes(self, *args):
            pass

        def withdraw(self):
            pass

    monkeypatch.setattr(pipeline_module.tk, "Tk", FakeRoot)
    monkeypatch.setattr(pipeline_module.tk, "Toplevel", FakeToplevel)
    monkeypatch.setattr(
        pipeline_module,
        "SectorWheel",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        ObserverWithSectorWheel, "setup_messagebox", lambda self: None
    )
    wheel = ObserverWithSectorWheel(
        SimpleNamespace(quit=False, action_output="desktop"),
        radius=100,
    )

    wheel.start()
    assert mainloop_started.wait(1)
    wheel_thread = wheel._thread
    assert wheel_thread.is_alive()

    wheel.stop()

    assert roots[0].destroyed.is_set()
    assert any(delay == 0 for delay, _ in roots[0].after_calls)
    assert not wheel_thread.is_alive()
    assert wheel._thread is None


def test_wheel_stop_preserves_worker_error_when_destroy_request_fails():
    worker_error = OSError("wheel callback failed")
    original_traceback = []

    def fail_in_worker():
        try:
            raise worker_error
        except OSError as error:
            original_traceback.append(error.__traceback__)
            return sys.exc_info()

    class FailingRoot:
        def after(self, delay, callback):
            raise RuntimeError("destroy request failed")

        def destroy(self):
            pass

    class JoinedThread:
        def __init__(self):
            self.joined = False

        def join(self):
            self.joined = True

    wheel = ObserverWithSectorWheel(
        SimpleNamespace(quit=False, action_output="desktop"),
        radius=100,
    )
    wheel.root = FailingRoot()
    wheel._thread = JoinedThread()
    wheel._worker_error = fail_in_worker()
    wheel_thread = wheel._thread

    with pytest.raises(OSError) as caught:
        wheel.stop()

    assert caught.value is worker_error
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert original_traceback[0] in traceback_chain
    assert wheel_thread.joined is True
    assert wheel._thread is None
    assert any("destroy request failed" in note for note in worker_error.__notes__)


def test_wheel_start_resets_per_run_selection_state(
    monkeypatch,
):
    created = []
    joined = []

    class InertThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            created.append(self)

        def start(self):
            pass

        def join(self):
            joined.append(self)

    monkeypatch.setattr(pipeline_module, "Thread", InertThread)
    subject = SimpleNamespace(quit=False)
    wheel = ObserverWithSectorWheel(subject, radius=100)
    wheel.current_categories = ["stale"]
    wheel.selected_sector = "stale"
    wheel.is_hidden = False

    wheel.start()
    wheel.stop()

    assert wheel.current_categories is None
    assert wheel.selected_sector is None
    assert wheel.is_hidden is True
    assert joined == created


def test_two_normal_runs_use_fresh_joined_per_run_resources(monkeypatch):
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.camera = None
    pipeline.camera_config = CameraConfig("opencv", 0, 640, 480, 30)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.show_gaze = False
    pipeline.screen_size = (640, 480)
    pipeline.destroy_window = lambda: None
    pipeline.call_after_while_loop = lambda: None
    opened_cameras = []
    closed_cameras = []
    wheel_threads = []
    joined_wheel_threads = []
    controller_threads = []
    joined_controller_threads = []

    class RunWheel:
        def start(self):
            self.thread = object()
            wheel_threads.append(self.thread)

        def stop(self):
            joined_wheel_threads.append(self.thread)
            self.thread = None

    class RunController:
        def update_screen_size(self, width, height):
            pass

        def start(self):
            self.thread = object()
            controller_threads.append(self.thread)

        def stop(self):
            joined_controller_threads.append(self.thread)
            self.thread = None

        def raise_if_failed(self):
            pass

    pipeline.wheel = RunWheel()
    pipeline.gaze_mouse_controller = RunController()
    pipeline.evaluate = lambda camera: setattr(
        pipeline, "end_calibration_signal", True
    )

    def open_source(config, platform):
        run_number = len(opened_cameras) + 1
        camera = SimpleNamespace(
            close=lambda: closed_cameras.append(run_number)
        )
        opened_cameras.append(camera)
        return camera

    monkeypatch.setattr(pipeline_module, "open_camera", open_source)
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (640, 480))
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: pytest.fail("normal runs must not release desktop input"),
    )

    pipeline.start_evaluation()
    pipeline.start_evaluation()

    assert len(opened_cameras) == 2
    assert closed_cameras == [1, 2]
    assert len({id(thread) for thread in wheel_threads}) == 2
    assert joined_wheel_threads == wheel_threads
    assert len({id(thread) for thread in controller_threads}) == 2
    assert joined_controller_threads == controller_threads
    assert pipeline.action_queue.empty()
    assert pipeline.camera is None
    assert pipeline.quit is False


def test_pipeline_camera_close_failure_retains_ownership_for_retry():
    close_error = RuntimeError("close failed")

    class RetryCamera:
        def __init__(self):
            self.calls = 0

        def close(self):
            self.calls += 1
            if self.calls == 1:
                raise close_error

    source = RetryCamera()
    pipeline = _pipeline_without_constructor()
    pipeline.camera = source

    with pytest.raises(RuntimeError) as caught:
        pipeline._close_camera()
    assert caught.value is close_error
    assert pipeline.camera is source

    pipeline._close_camera()
    assert source.calls == 2
    assert pipeline.camera is None


def test_terminal_quit_discards_queued_actions_before_release_all(
    monkeypatch,
):
    events = []
    pipeline = _real_action_without_constructor()
    _initialize_redesigned_lifecycle(pipeline)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.destroy_window = lambda: events.append("destroy")

    class Wheel:
        def stop(self):
            events.append("wheel.stop")
            pipeline.action_queue.put(
                SimpleNamespace(
                    keyname="late-click",
                    execute=lambda: events.append("late-click"),
                )
            )

    pipeline.wheel = Wheel()
    pipeline.action_queue.put(
        SimpleNamespace(
            keyname="queued-key",
            execute=lambda: events.append("queued-key"),
        )
    )
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: events.append("release_all"),
    )

    pipeline.quit_pipeline()

    assert events == ["wheel.stop", "release_all", "destroy"]
    assert pipeline.action_queue.empty()


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("caps", "caps_lock"), ("super", "win")],
)
def test_real_action_uses_direct_key_aliases(
    monkeypatch, alias, canonical
):
    pipeline = _real_action_without_constructor()
    pipeline.sys_mode_list = []
    calls = []
    monkeypatch.setattr(
        desktop, "supports_key", lambda key: key == canonical
    )
    monkeypatch.setattr(
        desktop, "key_down", lambda key: calls.append(("down", key))
    )
    monkeypatch.setattr(
        desktop, "key_up", lambda key: calls.append(("up", key))
    )
    monkeypatch.setattr(time, "sleep", lambda duration: None)

    _run_one_action(pipeline, Action(alias, OpType.KEYPRESS))

    assert calls == [("down", canonical), ("up", canonical)]


@pytest.mark.parametrize("key", ["fn", "definitely_unknown"])
def test_real_action_rejects_unknown_key_at_execution(monkeypatch, key):
    pipeline = _real_action_without_constructor()
    pipeline.sys_mode_list = []
    monkeypatch.setattr(desktop, "supports_key", lambda candidate: False)

    with pytest.raises(ValueError, match=key):
        pipeline._execute_action_once(Action(key, OpType.KEYPRESS))


def test_default_yaml_with_fn_loads_but_fn_execution_fails(monkeypatch):
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs" / "cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert "fn" in mapping["key_config"]["type"]["num2"]["wheel"]
    pipeline = _real_action_without_constructor()
    pipeline.sys_mode_list = list(mapping["key_config"])
    monkeypatch.setattr(desktop, "supports_key", lambda candidate: False)

    with pytest.raises(ValueError, match="fn"):
        pipeline._execute_action_once(Action("fn", OpType.KEYPRESS))




def _real_action_constructor_kwargs(monkeypatch):
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_regression_model",
        lambda self: setattr(self, "regression_model", None),
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "load_model_from_weights",
        lambda self: None,
    )
    monkeypatch.setattr(
        IntegratedRegressionMediaPipeline,
        "get_mediapipe",
        lambda self: object(),
    )
    monkeypatch.setattr(
        pipeline_module, "ExpressionEvaluator", lambda config: object()
    )
    return {
        "gaze_config": {},
        "mouse_control_config": {},
        "wheel_config": {},
        "head_angles_center": {},
        "head_angles_scale": {},
        "expression_evaluator_config": {},
        "weights": "unused.param",
        "device": "cpu",
        "camera_backend": {"linux": "opencv", "win32": "opencv"},
        "camera_width": 640,
        "camera_height": 480,
        "camera_fps": 30,
        "screen_size": (1920, 1080),
    }


def test_real_action_routes_platforms_and_rejects_missing_config(
    monkeypatch,
):
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    common = _real_action_constructor_kwargs(monkeypatch)
    robot_config = mapping["robot_action_config"]
    windows_key_config = mapping["key_config"]

    linux_pipeline = RealAction(
        action_platform="linux",
        robot_action_config=robot_config,
        robot_wheel_config=mapping["robot_wheel_config"],
        configuration=windows_key_config,
        **common,
    )
    assert linux_pipeline.action_output == "robot_terminal"
    assert linux_pipeline.sys_mode == "robot"
    assert linux_pipeline.sys_mode_list == ["robot"]

    windows_pipeline = RealAction(
        action_platform="win32",
        robot_action_config=robot_config,
        configuration=windows_key_config,
        sys_mode="game_cs",
        **common,
    )
    assert windows_pipeline.action_output == "desktop"
    assert windows_pipeline.sys_mode == "game_cs"

    with pytest.raises(ValueError, match="robot_action_config is required"):
        RealAction(action_platform="linux", **common)
    with pytest.raises(ValueError, match="configuration is required"):
        RealAction(
            action_platform="win32",
            robot_action_config=robot_config,
            **common,
        )
    with pytest.raises(RuntimeError, match="unsupported action platform"):
        RealAction(action_platform="darwin", **common)


def test_default_yaml_builds_fullscreen_robot_and_fixed_windows_wheel(
    monkeypatch,
):
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    common = _real_action_constructor_kwargs(monkeypatch)
    common["wheel_config"] = mapping["wheel_config"]
    robot_wheel_config = mapping["robot_wheel_config"]

    linux_pipeline = RealAction(
        action_platform="linux",
        robot_action_config=mapping["robot_action_config"],
        robot_wheel_config=robot_wheel_config,
        configuration=mapping["key_config"],
        **common,
    )
    windows_pipeline = RealAction(
        action_platform="win32",
        robot_action_config=mapping["robot_action_config"],
        robot_wheel_config=robot_wheel_config,
        configuration=mapping["key_config"],
        **common,
    )

    robot_wheel_config["layout"] = "changed_after_construction"
    assert linux_pipeline.wheel.layout == "fullscreen_cardinal"
    assert linux_pipeline.robot_wheel_config == {
        "layout": "fullscreen_cardinal",
        "selection": "head_pose",
        "yaw_threshold_degrees": 12.0,
        "pitch_threshold_degrees": 18.0,
    }
    assert windows_pipeline.wheel.radius == 1000


@pytest.mark.parametrize(
    ("robot_wheel_config", "error_type", "message"),
    [
        (None, ValueError, r"robot_wheel_config\.layout"),
        ([], TypeError, r"robot_wheel_config"),
        ({}, ValueError, r"robot_wheel_config\.layout"),
        (
            {
                "layout": "fullscreen_cardinal",
                "selection": "head_pose",
                "yaw_threshold_degrees": 12.0,
                "pitch_threshold_degrees": 10.0,
                "font": "Arial",
            },
            ValueError,
            r"robot_wheel_config\.font",
        ),
        (
            {
                "layout": True,
                "selection": "head_pose",
                "yaw_threshold_degrees": 12.0,
                "pitch_threshold_degrees": 10.0,
            },
            TypeError,
            r"robot_wheel_config\.layout",
        ),
        (
            {
                "layout": "fullscreen_cardinal",
                "selection": "gaze",
                "yaw_threshold_degrees": 12.0,
                "pitch_threshold_degrees": 10.0,
            },
            ValueError,
            r"robot_wheel_config\.selection",
        ),
        (
            {
                "layout": "fullscreen_cardinal",
                "selection": "head_pose",
                "yaw_threshold_degrees": True,
                "pitch_threshold_degrees": 10.0,
            },
            TypeError,
            r"robot_wheel_config\.yaw_threshold_degrees",
        ),
        (
            {
                "layout": "fullscreen_cardinal",
                "selection": "head_pose",
                "yaw_threshold_degrees": 46.0,
                "pitch_threshold_degrees": 10.0,
            },
            ValueError,
            r"robot_wheel_config\.yaw_threshold_degrees",
        ),
    ],
)
def test_linux_rejects_invalid_robot_wheel_config_at_construction(
    monkeypatch, robot_wheel_config, error_type, message
):
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    common = _real_action_constructor_kwargs(monkeypatch)
    common["wheel_config"] = mapping["wheel_config"]

    with pytest.raises(error_type, match=message):
        RealAction(
            action_platform="linux",
            robot_action_config=mapping["robot_action_config"],
            robot_wheel_config=robot_wheel_config,
            configuration=mapping["key_config"],
            **common,
        )

def test_windows_does_not_require_or_consume_robot_wheel_config(monkeypatch):
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    common = _real_action_constructor_kwargs(monkeypatch)
    common["wheel_config"] = mapping["wheel_config"]

    pipeline = RealAction(
        action_platform="win32",
        robot_action_config=mapping["robot_action_config"],
        robot_wheel_config={"radius": False, "unknown": object()},
        configuration=mapping["key_config"],
        **common,
    )

    assert pipeline.wheel.radius == 1000




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


def test_real_action_forces_robot_controller_to_internal_gaze(
    monkeypatch,
):
    captured = []

    class FakeController:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr(
        controller_module, "GazeMouseController", FakeController
    )
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    linux_config = {}
    windows_config = {}
    common = _real_action_constructor_kwargs(monkeypatch)

    linux_pipeline = RealAction(
        action_platform="linux",
        robot_action_config=mapping["robot_action_config"],
        robot_wheel_config=mapping["robot_wheel_config"],
        configuration=mapping["key_config"],
        mouse_control_config=linux_config,
        **{key: value for key, value in common.items()
           if key != "mouse_control_config"},
    )
    linux_kwargs = captured[-1]

    windows_pipeline = RealAction(
        action_platform="win32",
        robot_action_config=mapping["robot_action_config"],
        configuration=mapping["key_config"],
        mouse_control_config=windows_config,
        **{key: value for key, value in common.items()
           if key != "mouse_control_config"},
    )
    windows_kwargs = captured[-1]

    assert linux_kwargs["desktop_pointer_control"] is False
    assert linux_kwargs["select_wheel_using_head"] is False
    assert windows_kwargs.get("desktop_pointer_control", True) is True
    assert linux_config == {}
    assert windows_config == {}
    assert linux_pipeline.uses_desktop_input is False
    assert windows_pipeline.uses_desktop_input is True


@pytest.mark.parametrize(
    "field_name",
    ["desktop_pointer_control", "select_wheel_using_head"],
)
def test_real_action_rejects_robot_desktop_mouse_config(
    monkeypatch, field_name
):
    captured = []

    class FakeController:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    monkeypatch.setattr(
        controller_module, "GazeMouseController", FakeController
    )
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    mouse_control_config = {field_name: True}
    common = _real_action_constructor_kwargs(monkeypatch)

    with pytest.raises(ValueError, match=field_name):
        RealAction(
            action_platform="linux",
            robot_action_config=mapping["robot_action_config"],
            robot_wheel_config=mapping["robot_wheel_config"],
            configuration=mapping["key_config"],
            mouse_control_config=mouse_control_config,
            **{key: value for key, value in common.items()
               if key != "mouse_control_config"},
        )

    assert mouse_control_config == {field_name: True}
    assert captured == []


def test_robot_move_mouse_discards_gaze_prediction(monkeypatch):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.predicted_position = (321, 123)
    pipeline.mouse_dict = {"x": 1, "y": 2}
    monkeypatch.setattr(
        desktop,
        "get_pointer_position",
        lambda: pytest.fail("robot mode called desktop.get_pointer_position"),
    )

    pipeline.move_mouse()

    assert pipeline.mouse_dict is None


def test_robot_quit_does_not_release_desktop_input(monkeypatch):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.action_queue = queue.Queue()
    calls = []
    pipeline.wheel = SimpleNamespace(stop=lambda: calls.append("wheel.stop"))
    pipeline.destroy_window = lambda: calls.append("destroy")
    _forbid_robot_desktop_calls(monkeypatch)

    pipeline.quit_pipeline()

    assert calls == ["wheel.stop", "destroy"]


def _fullscreen_head_wheel(monkeypatch, pipeline):
    overlay = SimpleNamespace(
        show=lambda labels: None,
        select=lambda index: None,
        hide=lambda: None,
        raise_if_failed=lambda: None,
        stop=lambda: None,
    )
    monkeypatch.setattr(
        cardinal_module,
        "CardinalOverlay",
        lambda screen_size: overlay,
    )
    pipeline.screen_size = (1920, 1080)
    pipeline.head_angles = {"pitch": 0.0, "yaw": 0.0}
    return FullscreenCardinalWheel(
        pipeline,
        yaw_threshold_degrees=12.0,
        pitch_threshold_degrees=10.0,
    )


def _publish_robot_wheel_observation(
    pipeline,
    *,
    face_detected=True,
    mouth_open_recognized=False,
    jaw_open=0.05,
    pitch=0.0,
    yaw=0.0,
):
    pipeline.robot_wheel_observation_generation += 1
    generation = pipeline.robot_wheel_observation_generation
    pipeline.robot_wheel_observation = (
        generation,
        face_detected,
        mouth_open_recognized if face_detected else None,
        jaw_open if face_detected else None,
        pitch if face_detected else None,
        yaw if face_detected else None,
    )


def test_robot_wheel_observation_marks_tracking_loss_explicitly():
    pipeline = _robot_pipeline_without_constructor()
    pipeline.face_observation_valid = False

    pipeline._publish_robot_wheel_observation()

    assert pipeline.robot_wheel_observation == (
        1, False, None, None, None, None
    )


def test_robot_wheel_observation_contains_fresh_face_control_values():
    pipeline = _robot_pipeline_without_constructor()
    pipeline.face_observation_valid = True
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": True}}
    )
    pipeline.features = {"jawOpen": 0.73}
    pipeline.head_angles = {"pitch": 4.0, "yaw": -13.0}

    pipeline._publish_robot_wheel_observation()

    assert pipeline.robot_wheel_observation == (
        1, True, True, 0.73, 4.0, -13.0
    )


def test_robot_actions_emit_seven_lines_from_expressions_and_head_pose(
    monkeypatch, capsys
):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.action_queue = queue.Queue()
    pipeline.destroy_window = lambda: None
    pipeline.mouse_control = True
    _forbid_robot_desktop_calls(monkeypatch)

    for expression_id in ("left_click", "num8", "extra"):
        pipeline.keys_dict = SimpleNamespace(
            state_dict={expression_id: transition("FT", value=True)}
        )
        pipeline.head_dict = SimpleNamespace(state_dict={})
        pipeline.decode()

    wheel_actions = [
        RobotAction("move_forward_step", "前进一步", "wheel"),
        RobotAction("move_backward_step", "后退一步", "wheel"),
        RobotAction("turn_left", "左转", "wheel"),
        RobotAction("turn_right", "右转", "wheel"),
    ]
    pipeline.wheel_categories = wheel_actions
    pipeline.key_keeps_wheel_opening = "numlock"
    pipeline.wheel_layout_type = "cardinal"
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": True}}
    )

    sector_wheel = _fullscreen_head_wheel(monkeypatch, pipeline)
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel._thread = None
    wheel._worker_error = None
    wheel.lock = threading.Lock()
    wheel.current_categories = None
    wheel.selected_sector = None
    wheel.is_hidden = True
    wheel.last_robot_observation_generation = None
    wheel.subject = pipeline
    wheel.sector_wheel = sector_wheel
    wheel.root = SimpleNamespace(after=lambda *args: None)
    pipeline.wheel = wheel

    for head_pose, expected_action in (
        ({"pitch": 11.0, "yaw": 0.0}, wheel_actions[0]),
        ({"pitch": -11.0, "yaw": 0.0}, wheel_actions[1]),
        ({"pitch": 0.0, "yaw": 13.0}, wheel_actions[2]),
        ({"pitch": 0.0, "yaw": -13.0}, wheel_actions[3]),
    ):
        pipeline.keys_dict.state_dict["numlock"]["v"] = True
        wheel.sector_wheel_main_loop()
        assert wheel.is_hidden is False
        pipeline.keys_dict.state_dict["numlock"]["v"] = False

        for _ in range(5):
            _publish_robot_wheel_observation(
                pipeline,
                mouth_open_recognized=False,
                jaw_open=0.05,
                **head_pose,
            )
            wheel.sector_wheel_main_loop()
        assert sector_wheel.selected_sector is expected_action
        assert wheel.is_hidden is False

        for _ in range(3):
            _publish_robot_wheel_observation(
                pipeline,
                mouth_open_recognized=True,
                jaw_open=0.7,
            )
            wheel.sector_wheel_main_loop()
        for _ in range(5):
            _publish_robot_wheel_observation(
                pipeline,
                mouth_open_recognized=False,
                jaw_open=0.05,
            )
            wheel.sector_wheel_main_loop()
        assert wheel.is_hidden is True
        pipeline._drain_actions()

    pipeline.quit_pipeline()

    assert capsys.readouterr().out.splitlines() == [
        "[ROBOT_ACTION] id=wave label=挥手 source=expression",
        "[ROBOT_ACTION] id=dance label=舞蹈 source=expression",
        "[ROBOT_ACTION] id=stop label=停止 source=expression",
        "[ROBOT_ACTION] id=move_forward_step label=前进一步 source=wheel",
        "[ROBOT_ACTION] id=move_backward_step label=后退一步 source=wheel",
        "[ROBOT_ACTION] id=turn_left label=左转 source=wheel",
        "[ROBOT_ACTION] id=turn_right label=右转 source=wheel",
    ]


def test_robot_wheel_consumes_held_head_pose_in_fresh_open_cycles(
    monkeypatch, capsys
):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.quit = False
    pipeline.action_queue = queue.Queue()
    selected = RobotAction("turn_left", "左转", "wheel")
    pipeline.wheel_categories = [selected] * 4
    pipeline.key_keeps_wheel_opening = "numlock"
    pipeline.wheel_layout_type = "cardinal"
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": True}}
    )
    sector_wheel = _fullscreen_head_wheel(monkeypatch, pipeline)
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel._worker_error = None
    wheel.lock = threading.Lock()
    wheel.is_hidden = True
    wheel.last_robot_observation_generation = None
    wheel.subject = pipeline
    wheel.sector_wheel = sector_wheel
    wheel.root = SimpleNamespace(after=lambda *args: None)

    def open_wheel():
        pipeline.keys_dict.state_dict["numlock"]["v"] = True
        wheel.sector_wheel_main_loop()
        pipeline.keys_dict.state_dict["numlock"]["v"] = False
        assert wheel.is_hidden is False

    def observe(count, **observation):
        for _ in range(count):
            _publish_robot_wheel_observation(pipeline, **observation)
            wheel.sector_wheel_main_loop()

    def run_selected_cycle(head_pose):
        open_wheel()
        observe(
            5,
            mouth_open_recognized=False,
            jaw_open=0.05,
            **head_pose,
        )
        observe(3, mouth_open_recognized=True, jaw_open=0.7)
        observe(5, mouth_open_recognized=False, jaw_open=0.05)
        assert wheel.is_hidden is True
        pipeline._drain_actions()

    run_selected_cycle({"pitch": 0.0, "yaw": 14.0})
    run_selected_cycle({"pitch": 0.0, "yaw": 14.0})

    open_wheel()
    observe(30, mouth_open_recognized=False, jaw_open=0.05)
    assert wheel.is_hidden is True
    pipeline._drain_actions()

    assert capsys.readouterr().out.splitlines() == [
        "[ROBOT_ACTION] id=turn_left label=左转 source=wheel",
        "[ROBOT_ACTION] id=turn_left label=左转 source=wheel",
        "[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel",
    ]


def _robot_pipeline_without_constructor():
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    pipeline = _real_action_without_constructor()
    pipeline.action_output = "robot_terminal"
    pipeline.uses_desktop_input = False
    pipeline.op_xy = (None, None)
    pipeline.op_xy_generation = 0
    pipeline.published_op_xy_generation = 0
    pipeline.key_control = True
    pipeline.robot_action_config = mapping["robot_action_config"]
    pipeline.robot_wheel_observation_generation = 0
    pipeline.robot_wheel_observation = None
    return pipeline


def transition(cp, value):
    return {
        "diff": True,
        "cp": cp,
        "v": value,
        "time_True": time.time(),
    }


@pytest.mark.parametrize(
    ("expression_id", "expected_id", "expected_label"),
    [
        ("left_click", "wave", "挥手"),
        ("num8", "dance", "舞蹈"),
        ("extra", "stop", "停止"),
    ],
)
def test_robot_direct_expression_emits_once_on_rising_edge(
    capsys, expression_id, expected_id, expected_label
):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={expression_id: transition("FT", value=True)}
    )
    pipeline.head_dict = SimpleNamespace(state_dict={})

    pipeline.decode()
    pipeline.keys_dict.state_dict[expression_id] = transition(
        "TT", value=True
    )
    pipeline.decode()
    pipeline.keys_dict.state_dict[expression_id] = transition(
        "TF", value=False
    )
    pipeline.decode()

    assert capsys.readouterr().out == (
        f"[ROBOT_ACTION] id={expected_id} "
        f"label={expected_label} source=expression\n"
    )


def test_robot_unconfigured_expression_is_silent(capsys):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"num1": transition("FT", value=True)}
    )
    pipeline.head_dict = SimpleNamespace(state_dict={})

    pipeline.decode()

    assert capsys.readouterr().out == ""



def test_default_robot_config_has_exact_action_contract():
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml").read_text(
            encoding="utf-8"
        )
    )
    robot = mapping["robot_action_config"]
    assert robot["actions"] == {
        "move_forward_step": "前进一步",
        "move_backward_step": "后退一步",
        "turn_left": "左转",
        "turn_right": "右转",
        "wave": "挥手",
        "dance": "舞蹈",
        "stop": "停止",
    }
    assert robot["expressions"] == {
        "numlock": {
            "wheel": [
                "move_forward_step",
                "move_backward_step",
                "turn_left",
                "turn_right",
            ]
        },
        "left_click": {"action": "wave"},
        "num8": {"action": "dance"},
        "extra": {"action": "stop"},
    }


def test_screen_to_canvas_subtracts_only_window_origin():
    wheel = _cardinal_wheel_without_tk(radius=400)
    wheel.messagebox = SimpleNamespace(
        winfo_rootx=lambda: 560,
        winfo_rooty=lambda: 140,
    )

    assert wheel._screen_to_canvas(960, 540) == (400, 400)


@pytest.mark.parametrize(
    ("screen_point", "expected_index"),
    [
        ((1400, 550), 0),
        ((1400, 1150), 1),
        ((1100, 850), 2),
        ((1700, 850), 3),
    ],
)
def test_screen_to_canvas_preserves_cardinal_positions_on_large_screen(
    screen_point, expected_index
):
    wheel = _cardinal_wheel_without_tk(radius=400)
    wheel.messagebox = SimpleNamespace(
        winfo_rootx=lambda: 1000,
        winfo_rooty=lambda: 450,
    )

    local_x, local_y = wheel._screen_to_canvas(*screen_point)

    assert wheel.get_cardinal_from_mouse_position(
        SimpleNamespace(x=local_x, y=local_y)
    ) == expected_index


def test_screen_to_canvas_propagates_window_origin_errors():
    wheel = _cardinal_wheel_without_tk(radius=400)

    def fail_rootx():
        raise RuntimeError("Tk root coordinate failed")

    wheel.messagebox = SimpleNamespace(
        winfo_rootx=fail_rootx,
        winfo_rooty=lambda: 140,
    )

    with pytest.raises(RuntimeError, match="Tk root coordinate failed"):
        wheel._screen_to_canvas(960, 540)


def test_robot_numlock_opens_cardinal_wheel_with_robot_actions():
    pipeline = _robot_pipeline_without_constructor()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": transition("FT", value=True)}
    )
    pipeline.head_dict = SimpleNamespace(state_dict={})

    pipeline.decode()

    assert pipeline.wheel_layout_type == "cardinal"
    assert pipeline.key_keeps_wheel_opening == "numlock"
    assert pipeline.wheel_categories == [
        RobotAction("move_forward_step", "前进一步", "wheel"),
        RobotAction("move_backward_step", "后退一步", "wheel"),
        RobotAction("turn_left", "左转", "wheel"),
        RobotAction("turn_right", "右转", "wheel"),
    ]


def test_robot_wheel_open_does_not_move_desktop_pointer(monkeypatch):
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel.lock = threading.Lock()
    wheel.current_categories = None
    wheel.selected_sector = None
    wheel.is_hidden = True
    updates = []

    def update_categories(categories, layout_type):
        updates.append((categories, layout_type))
        wheel.should_run = False

    wheel.sector_wheel = SimpleNamespace(update_categories=update_categories)
    categories = [RobotAction("turn_left", "左转", "wheel")] * 4
    wheel.subject = SimpleNamespace(
        keys_dict=SimpleNamespace(state_dict={"numlock": {"v": True}}),
        wheel_categories=categories,
        key_keeps_wheel_opening="numlock",
        mid_point=(960, 540),
        wheel_layout_type="cardinal",
        action_output="robot_terminal",
        quit=False,
    )
    monkeypatch.setattr(pipeline_module.time, "sleep", lambda duration: None)
    monkeypatch.setattr(
        desktop,
        "move_pointer",
        lambda *args, **kwargs: pytest.fail("robot wheel moved the pointer"),
    )

    wheel.sector_wheel_main_loop()

    assert updates == [(categories, "cardinal")]


def test_robot_wheel_counts_each_camera_observation_once():
    pipeline = _robot_pipeline_without_constructor()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": False}}
    )
    pipeline.key_keeps_wheel_opening = "numlock"
    pipeline.quit = False
    pipeline.wheel_categories = ["a", "b", "c", "d"]
    _publish_robot_wheel_observation(pipeline)
    observations = []
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel.lock = threading.Lock()
    wheel.is_hidden = False
    wheel.last_robot_observation_generation = None
    wheel.subject = pipeline
    wheel.sector_wheel = SimpleNamespace(
        observe_control_frame=lambda **kwargs: observations.append(kwargs),
    )
    wheel.root = SimpleNamespace(after=lambda *args: None)

    wheel.sector_wheel_main_loop()
    wheel.sector_wheel_main_loop()

    assert len(observations) == 1


def test_robot_wheel_selection_keeps_robot_action_identity_and_emits_once(
    capsys
):
    pipeline = _robot_pipeline_without_constructor()
    selected = RobotAction("turn_left", "左转", "wheel")
    pipeline.action_queue = queue.Queue()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": False}}
    )
    pipeline.key_keeps_wheel_opening = "numlock"
    pipeline.quit = False
    pipeline.wheel_categories = [selected] * 4
    pipeline.wheel_layout_type = "cardinal"
    _publish_robot_wheel_observation(pipeline)
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel.lock = threading.Lock()
    wheel.current_categories = None
    wheel.selected_sector = None
    wheel.is_hidden = False
    wheel.last_robot_observation_generation = None
    wheel.subject = pipeline
    wheel.sector_wheel = SimpleNamespace(
        selected_sector=selected,
        observe_control_frame=lambda **kwargs: "submit",
        hide=lambda: setattr(wheel, "should_run", False),
    )
    wheel.root = SimpleNamespace(after=lambda *args: None)

    wheel.sector_wheel_main_loop()

    assert pipeline.action_queue.get_nowait() is selected
    pipeline.action_queue.put(selected)
    pipeline._drain_actions()
    assert capsys.readouterr().out == (
        "[ROBOT_ACTION] id=turn_left label=左转 source=wheel\n"
    )


def test_robot_wheel_cancel_is_silent_except_for_explicit_cancel_line(capsys):
    pipeline = _robot_pipeline_without_constructor()
    pipeline.action_queue = queue.Queue()
    pipeline.keys_dict = SimpleNamespace(
        state_dict={"numlock": {"v": False}}
    )
    pipeline.key_keeps_wheel_opening = "numlock"
    pipeline.quit = False
    pipeline.wheel_categories = []
    _publish_robot_wheel_observation(pipeline)
    wheel = object.__new__(ObserverWithSectorWheel)
    wheel.should_run = True
    wheel.lock = threading.Lock()
    wheel.current_categories = None
    wheel.selected_sector = None
    wheel.is_hidden = False
    wheel.last_robot_observation_generation = None
    wheel.subject = pipeline
    wheel.sector_wheel = SimpleNamespace(
        selected_sector=None,
        observe_control_frame=lambda **kwargs: "cancel",
        hide=lambda: setattr(wheel, "should_run", False),
    )
    wheel.root = SimpleNamespace(after=lambda *args: None)

    wheel.sector_wheel_main_loop()

    assert pipeline.action_queue.empty()
    assert capsys.readouterr().out == (
        "[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel\n"
    )


def test_robot_wheel_rejects_non_robot_selection():
    pipeline = _robot_pipeline_without_constructor()

    with pytest.raises(TypeError, match="RobotAction"):
        pipeline.make_wheel_action("turn_left")


def test_windows_wheel_selection_remains_keypress_action():
    pipeline = _real_action_without_constructor()

    action = pipeline.make_wheel_action("turn_left")

    assert isinstance(action, Action)
    assert action.keyname == "turn_left"
    assert action.op_type == OpType.KEYPRESS


def test_robot_output_rejects_desktop_action():
    pipeline = _robot_pipeline_without_constructor()

    with pytest.raises(TypeError, match="requires RobotAction"):
        pipeline._execute_action_once(Action("space", OpType.KEYPRESS))


def test_desktop_output_rejects_robot_action():
    pipeline = _real_action_without_constructor()

    with pytest.raises(TypeError, match="rejects RobotAction"):
        pipeline._execute_action_once(
            RobotAction("wave", "挥手", "expression")
        )
