import ast
import builtins
import inspect
import queue
import sys
import threading
import time
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
    pipeline = object.__new__(IntegratedRegressionMediaPipeline)
    pipeline._lifecycle_lock = threading.RLock()
    return pipeline


def _real_action_without_constructor():
    pipeline = object.__new__(RealAction)
    pipeline._lifecycle_lock = threading.RLock()
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
    wheel = ObserverWithSectorWheel(SimpleNamespace(quit=False), radius=100)

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

    wheel = ObserverWithSectorWheel(SimpleNamespace(quit=False), radius=100)
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


def test_redesign_removes_persistent_action_worker_and_token_protocol():
    source = Path(pipeline_module.__file__).read_text()

    for obsolete_name in (
        "_action_thread",
        "_action_condition",
        "_published_action_tokens",
        "_completed_action_tokens",
        "_action_worker_error",
        "_publish_action_token",
        "raise_action_worker_if_failed",
        "loop_queue",
        "def loop_key",
    ):
        assert obsolete_name not in source
    assert (
        "threading.Thread(target=self.wheel.run_sector_wheel" not in source
    )


def test_windows_desktop_and_overlay_routes_remain_lazy_on_linux():
    desktop_source = Path(desktop.__file__).read_text()
    pipeline_source = Path(pipeline_module.__file__).read_text()
    pipeline_tree = ast.parse(pipeline_source)

    assert '"my_model_arch.cpu_fast.desktop.win32"' in desktop_source
    assert "from .gaze_show_utils import GazeOverlay" in inspect.getsource(
        RealAction.start_gaze_display
    )
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "win32" in ast.unparse(node)
        for node in pipeline_tree.body
    )
