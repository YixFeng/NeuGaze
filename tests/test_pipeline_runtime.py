import ast
import builtins
import inspect
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_model_arch.cpu_fast import desktop
from my_model_arch.cpu_fast.camera import CameraConfig
from my_model_arch.cpu_fast import pipeline as pipeline_module
from my_model_arch.cpu_fast.keyboard_utils import Action, OpType
from my_model_arch.cpu_fast.pipeline import (
    BindKeys,
    IntegratedRegressionMediaPipeline,
    ObserverWithSectorWheel,
    RealAction,
)


def _pipeline_without_constructor():
    return object.__new__(IntegratedRegressionMediaPipeline)


def _real_action_without_constructor():
    return object.__new__(RealAction)


def _initialize_action_sync_state(pipeline):
    pipeline.action_queue = []
    pipeline.loop_queue = []
    pipeline._action_thread = None
    pipeline._action_worker_error = None
    pipeline._action_condition = threading.Condition()
    pipeline._published_action_tokens = 0
    pipeline._completed_action_tokens = 0
    pipeline._action_worker_idle = False


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


def test_quit_joins_action_worker_before_releasing_desktop(monkeypatch):
    calls = []

    class ActionThread:
        def join(self):
            calls.append("action_worker.join")

    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline._action_thread = ActionThread()
    pipeline._action_worker_error = None
    pipeline.destroy_window = lambda: calls.append("windows")
    monkeypatch.setattr(
        desktop, "release_all", lambda: calls.append("desktop.release_all")
    )

    pipeline.quit_pipeline()

    assert calls.index("action_worker.join") < calls.index(
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


def test_pipeline_has_no_live_platform_specific_input_dependency():
    source = Path(pipeline_module.__file__).read_text()
    tree = ast.parse(source)
    forbidden_names = {
        "pg",
        "pyautogui",
        "keyboard",
        "win32api",
        "win32con",
        "ctypes",
    }

    assert not any(
        isinstance(node, ast.Name) and node.id in forbidden_names
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.alias) and node.name in forbidden_names
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0]
        in {"pyautogui", "keyboard", "win32", "ctypes"}
        for node in ast.walk(tree)
    )


def _run_one_action(pipeline, action):
    pipeline.sys_mode_list = []
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


def test_hotkey_uses_explicit_down_and_reverse_up(monkeypatch):
    pipeline = _real_action_without_constructor()
    calls = []
    action = Action("ctrl+a", OpType.NONE)
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
        _run_one_action(pipeline, Action("ctrl+shift+a", OpType.NONE))

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
        _run_one_action(pipeline, Action("ctrl+a", OpType.NONE))

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

    _run_one_action(pipeline, Action("scroll_up", OpType.NONE))

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
    pipeline.wheel = SimpleNamespace(should_run=True)
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
    assert pipeline.wheel.should_run is True


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
    pipeline.wheel = SimpleNamespace(should_run=True)
    pipeline.gaze_mouse_controller = SimpleNamespace(
        stop=lambda: calls.append("controller.stop")
    )
    pipeline.destroy_window = lambda: calls.append("windows")
    pipeline._action_worker_error = None

    class ActionThread:
        def join(self):
            assert pipeline.quit is True
            assert pipeline.wheel.should_run is False
            calls.append("action_worker.join")

    pipeline._action_thread = ActionThread()

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
        "action_worker.join",
        "desktop.release_all",
        "controller.stop",
        "camera.close",
        "windows",
    ]
    assert pipeline.quit is True
    assert pipeline.wheel.should_run is False
    assert pipeline.camera is None
    if cancellation == "nested_calibrate":
        assert hotkey_calls == []
    elif cancellation == "quit_hotkey":
        assert hotkey_calls == [("esc", "q")]


def test_quit_notifies_action_worker_before_join(monkeypatch):
    calls = []
    pipeline = _pipeline_without_constructor()
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.camera = None
    pipeline.destroy_window = lambda: None
    pipeline._action_worker_error = None

    class RecordingCondition:
        def __enter__(self):
            calls.append("condition.enter")
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            calls.append("condition.exit")

        def notify_all(self):
            calls.append("condition.notify_all")

    class ActionThread:
        def join(self):
            assert pipeline.quit is True
            calls.append("action_worker.join")

    pipeline._action_condition = RecordingCondition()
    pipeline._action_thread = ActionThread()
    monkeypatch.setattr(desktop, "release_all", lambda: None)

    pipeline.quit_pipeline()

    assert calls == [
        "condition.enter",
        "condition.notify_all",
        "condition.exit",
        "action_worker.join",
    ]


def test_final_action_failure_crosses_normal_boundary_with_original_traceback(
    monkeypatch,
):
    calls = []
    pipeline = _real_action_without_constructor()
    _initialize_action_sync_state(pipeline)
    pipeline.camera = SimpleNamespace(
        close=lambda: calls.append("camera.close")
    )
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.show_gaze = False
    pipeline.screen_size = (640, 480)
    pipeline.sys_mode_list = []
    pipeline.wheel = SimpleNamespace(should_run=True)
    pipeline.destroy_window = lambda: calls.append("windows")
    pipeline.gaze_mouse_controller = SimpleNamespace(
        raise_if_failed=lambda: None,
        update_screen_size=lambda width, height: None,
        start=lambda: calls.append("controller.start"),
        stop=lambda: calls.append("controller.stop"),
    )

    source_error = OSError("final action failed")
    source_traceback = []
    action_started = threading.Event()
    boundary_reached = threading.Event()
    evaluation_count = 0

    def fail_final_action():
        action_started.set()
        assert boundary_reached.wait(1)
        try:
            raise source_error
        except OSError as error:
            source_traceback.append(error.__traceback__)
            raise

    def evaluate(camera):
        nonlocal evaluation_count
        evaluation_count += 1
        if evaluation_count == 2:
            assert action_started.wait(1)
            pipeline.end_calibration_signal = True

    def publish_final_action():
        with pipeline._action_condition:
            pipeline.action_queue.append(
                SimpleNamespace(
                    keyname="a",
                    execute=fail_final_action,
                )
            )
            pipeline.loop_queue.append(1)
            pipeline._published_action_tokens += 1
            pipeline._action_condition.notify_all()

    pipeline.evaluate = evaluate
    pipeline.call_after_each_eval_loop = publish_final_action
    pipeline.call_after_while_loop = boundary_reached.set
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: calls.append("desktop.release_all"),
    )

    try:
        with pytest.raises(OSError) as caught:
            pipeline.start_evaluation()
    finally:
        boundary_reached.set()
        action_thread = getattr(pipeline, "_action_thread", None)
        if action_thread is not None:
            action_thread.join(1)

    assert caught.value is source_error
    traceback = caught.value.__traceback__
    traceback_chain = []
    while traceback is not None:
        traceback_chain.append(traceback)
        traceback = traceback.tb_next
    assert source_traceback[0] in traceback_chain
    assert calls == [
        "controller.start",
        "desktop.release_all",
        "controller.stop",
        "camera.close",
        "windows",
    ]
    assert pipeline.quit is True
    assert pipeline.wheel.should_run is False
    assert pipeline.camera is None
    assert not pipeline._action_thread.is_alive()


def test_successful_final_actions_complete_before_two_reusable_runs_return(
    monkeypatch,
):
    pipeline = _real_action_without_constructor()
    _initialize_action_sync_state(pipeline)
    close_calls = []
    cameras = [
        SimpleNamespace(close=lambda: close_calls.append("camera-1")),
        SimpleNamespace(close=lambda: close_calls.append("camera-2")),
    ]
    executed = []
    action_started = [threading.Event(), threading.Event()]
    boundary_reached = [threading.Event(), threading.Event()]
    evaluation_counts = [0, 0]

    class RunController:
        def __init__(self):
            self.start_count = 0
            self.stop_count = 0

        def raise_if_failed(self):
            pass

        def update_screen_size(self, width, height):
            pass

        def start(self):
            self.start_count += 1

        def stop(self):
            self.stop_count += 1

    controller = RunController()
    pipeline.camera = None
    pipeline.camera_config = CameraConfig("opencv", 0, 640, 480, 30)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.show_gaze = False
    pipeline.screen_size = (640, 480)
    pipeline.sys_mode_list = []
    pipeline.wheel = SimpleNamespace(should_run=True)
    pipeline.destroy_window = lambda: None
    pipeline.gaze_mouse_controller = controller

    def current_run():
        return controller.start_count - 1

    def execute_action(run_id):
        action_started[run_id].set()
        assert boundary_reached[run_id].wait(1)
        executed.append(run_id)

    def evaluate(camera):
        run_id = current_run()
        evaluation_counts[run_id] += 1
        if evaluation_counts[run_id] == 2:
            assert action_started[run_id].wait(1)
            pipeline.end_calibration_signal = True

    def publish_action():
        run_id = current_run()
        with pipeline._action_condition:
            pipeline.action_queue.append(
                SimpleNamespace(
                    keyname="a",
                    execute=lambda: execute_action(run_id),
                )
            )
            pipeline.loop_queue.append(1)
            pipeline._published_action_tokens += 1
            pipeline._action_condition.notify_all()

    pipeline.evaluate = evaluate
    pipeline.call_after_each_eval_loop = publish_action
    pipeline.call_after_while_loop = (
        lambda: boundary_reached[current_run()].set()
    )
    monkeypatch.setattr(
        pipeline_module,
        "open_camera",
        lambda config, platform: cameras.pop(0),
    )
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (640, 480))
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: pytest.fail("normal run must not release desktop input"),
    )

    try:
        pipeline.start_evaluation()
        action_thread = pipeline._action_thread
        pipeline.start_evaluation()

        assert executed == [0, 1]
        assert pipeline._completed_action_tokens == 2
        assert pipeline._published_action_tokens == 2
        assert pipeline._action_thread is action_thread
        assert pipeline._action_thread.is_alive()
        assert controller.start_count == 2
        assert controller.stop_count == 2
        assert close_calls == ["camera-1", "camera-2"]
        assert pipeline.camera is None
        assert pipeline.quit is False
        assert pipeline.wheel.should_run is True
    finally:
        with pipeline._action_condition:
            pipeline.quit = True
            pipeline._action_condition.notify_all()
        action_thread = getattr(pipeline, "_action_thread", None)
        if action_thread is not None:
            action_thread.join(1)


def test_same_pipeline_reuses_action_worker_and_fresh_controller_run(
    monkeypatch,
):
    action_threads = []

    class ActionThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self.alive = False
            self.join_count = 0
            action_threads.append(self)

        def start(self):
            self.alive = True

        def is_alive(self):
            return self.alive

        def join(self):
            self.join_count += 1
            self.alive = False

    class RunController:
        def __init__(self):
            self.start_count = 0
            self.stop_count = 0
            self.stale_gaze = None
            self.executed_gaze = []

        def raise_if_failed(self):
            pass

        def update_screen_size(self, width, height):
            pass

        def start(self):
            self.start_count += 1
            if self.stale_gaze is not None:
                self.executed_gaze.append(self.stale_gaze)

        def stop(self):
            self.stop_count += 1
            self.stale_gaze = None

    close_calls = []
    cameras = [
        SimpleNamespace(close=lambda: close_calls.append("camera-1")),
        SimpleNamespace(close=lambda: close_calls.append("camera-2")),
    ]
    controller = RunController()
    pipeline = _real_action_without_constructor()
    pipeline.camera = None
    pipeline.camera_config = CameraConfig("opencv", 0, 640, 480, 30)
    pipeline.quit = False
    pipeline.end_calibration_signal = False
    pipeline.render_in_eval = False
    pipeline.open_windows = []
    pipeline.show_gaze = False
    pipeline.screen_size = (640, 480)
    pipeline._action_thread = None
    pipeline._action_worker_error = None
    pipeline.action_queue = []
    pipeline.loop_queue = []
    pipeline._action_condition = threading.Condition()
    pipeline._published_action_tokens = 0
    pipeline._completed_action_tokens = 0
    pipeline._action_worker_idle = False
    pipeline.gaze_mouse_controller = controller
    pipeline.wheel = SimpleNamespace(should_run=True)
    pipeline.destroy_window = lambda: None
    pipeline.call_after_while_loop = lambda: None

    def evaluate(camera):
        if controller.start_count == 1:
            controller.stale_gaze = (111, 222)
        pipeline.end_calibration_signal = True

    pipeline.evaluate = evaluate
    release_calls = []
    monkeypatch.setattr(pipeline_module, "Thread", ActionThread)
    monkeypatch.setattr(desktop, "get_screen_size", lambda: (640, 480))
    monkeypatch.setattr(
        pipeline_module,
        "open_camera",
        lambda config, platform: cameras.pop(0),
    )
    monkeypatch.setattr(pipeline_module.cv2, "waitKey", lambda delay: 0)
    monkeypatch.setattr(
        desktop,
        "release_all",
        lambda: release_calls.append("release"),
    )

    pipeline.start_evaluation()
    pipeline.start_evaluation()

    assert close_calls == ["camera-1", "camera-2"]
    assert pipeline.camera is None
    assert pipeline.quit is False
    assert pipeline.wheel.should_run is True
    assert len(action_threads) == 1
    assert action_threads[0].is_alive()
    assert action_threads[0].join_count == 0
    assert controller.start_count == 2
    assert controller.stop_count == 2
    assert controller.executed_gaze == []
    assert release_calls == []


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


def test_call_before_loop_stores_started_action_worker(monkeypatch):
    pipeline = _real_action_without_constructor()
    pipeline._action_thread = None
    pipeline._action_worker_error = None
    pipeline.quit = False
    pipeline.show_gaze = False
    pipeline.screen_size = (1920, 1080)
    pipeline.gaze_mouse_controller = SimpleNamespace(
        update_screen_size=lambda width, height: None,
        start=lambda: None,
    )
    created = []

    class ActionThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            self.started = False
            created.append(self)

        def start(self):
            self.started = True

        def is_alive(self):
            return self.started

    monkeypatch.setattr(pipeline_module, "Thread", ActionThread)
    monkeypatch.setattr(BindKeys, "call_before_while_loop", lambda self: None)

    pipeline.call_before_while_loop()

    assert pipeline._action_thread is created[0]
    assert pipeline._action_thread.target == pipeline.loop_key
    assert pipeline._action_thread.daemon is True
    assert pipeline._action_thread.started is True


def test_idle_action_worker_exits_after_quit_signal(monkeypatch):
    pipeline = _real_action_without_constructor()
    _initialize_action_sync_state(pipeline)
    pipeline.quit = False
    pipeline.sys_mode_list = []
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    worker = threading.Thread(target=pipeline.loop_key, daemon=True)

    try:
        with pipeline._action_condition:
            worker.start()
            assert pipeline._action_condition.wait_for(
                lambda: pipeline._action_worker_idle,
                timeout=1,
            )
            pipeline.quit = True
            pipeline._action_condition.notify_all()
        worker.join(0.5)
        assert not worker.is_alive()
        assert pipeline._action_worker_error is None
    finally:
        if worker.is_alive():
            with pipeline._action_condition:
                pipeline.quit = True
                pipeline._action_condition.notify_all()
            worker.join(1)


def test_action_worker_rethrows_original_error_and_traceback(monkeypatch):
    pipeline = _real_action_without_constructor()
    _initialize_action_sync_state(pipeline)
    pipeline.quit = False
    pipeline.loop_queue = [1]
    pipeline._published_action_tokens = 1
    pipeline.sys_mode_list = []
    source_error = OSError("desktop injection failed")
    source_traceback = []

    def fail():
        try:
            raise source_error
        except OSError as error:
            source_traceback.append(error.__traceback__)
            raise

    pipeline.action_queue.append(
        SimpleNamespace(keyname="a", execute=fail)
    )
    monkeypatch.setattr(desktop, "supports_key", lambda key: True)
    worker = threading.Thread(target=pipeline.loop_key, daemon=True)
    worker.start()
    worker.join(1)

    assert not worker.is_alive()
    assert pipeline.quit is True
    with pytest.raises(OSError) as caught:
        pipeline.raise_action_worker_if_failed()

    assert caught.value is source_error
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
    pipeline.loop_queue = []
    pipeline.gaze_mouse_controller = SimpleNamespace(
        raise_if_failed=lambda: calls.append("raise_if_failed"),
        stop=lambda: calls.append("stop"),
    )
    pipeline.raise_action_worker_if_failed = lambda: calls.append(
        "raise_action_worker_if_failed"
    )
    pipeline._publish_action_token = lambda: calls.append(
        "publish_action_token"
    )
    monkeypatch.setattr(
        BindKeys,
        "call_after_each_eval_loop",
        lambda self: calls.append("inherited"),
    )

    pipeline.call_after_each_eval_loop()

    assert calls == [
        "raise_action_worker_if_failed",
        "raise_if_failed",
        "inherited",
        "decode",
        "publish_action_token",
    ]
    assert pipeline.loop_queue == []
