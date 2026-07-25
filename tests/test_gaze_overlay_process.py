import ast
import builtins
import importlib
import queue
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from my_model_arch.cpu_fast import pipeline as pipeline_module
from my_model_arch.cpu_fast.pipeline import BindKeys, RealAction
from my_model_arch.cpu_fast import gaze_overlay_x11 as overlay_module
from my_model_arch.cpu_fast.gaze_overlay_x11 import GazeOverlay


class FakeControl:
    def __init__(self, messages=()):
        self.messages = list(messages)
        self.sent = []
        self.closed = False
        self.send_error = None
        self.reply_to_stop = False

    def poll(self, timeout=0):
        return bool(self.messages)

    def recv(self):
        return self.messages.pop(0)

    def send(self, message):
        if self.send_error is not None:
            raise self.send_error
        self.sent.append(message)
        if self.reply_to_stop and message == ("stop", None):
            self.messages.append(("stopped", None))

    def close(self):
        self.closed = True


class FakePointQueue(queue.Queue):
    def close(self):
        pass

    def join_thread(self):
        pass



class FakeProcess:
    def __init__(self, control, *, start_error=None, exit_on_join=False):
        self.control = control
        self.start_error = start_error
        self.exit_on_join = exit_on_join
        self.started = False
        self.alive = False
        self.exitcode = None
        self.join_timeouts = []
        self.terminated = False

    def start(self):
        if self.start_error is not None:
            raise self.start_error
        self.started = True
        self.alive = True

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)
        if self.exit_on_join and ("stop", None) in self.control.sent:
            self.alive = False
            self.exitcode = 0

    def terminate(self):
        self.terminated = True
        self.alive = False
        self.exitcode = -15


class FakeContext:
    def __init__(self, control, process):
        self.control = control
        self.child_control = FakeControl()
        self.process = process
        self.pipe_duplex = None
        self.queue_maxsize = None
        self.point_queue = None
        self.process_target = None
        self.process_args = None

    def Pipe(self, duplex):
        self.pipe_duplex = duplex
        return self.control, self.child_control

    def Queue(self, maxsize):
        self.queue_maxsize = maxsize
        self.point_queue = FakePointQueue(maxsize=maxsize)
        return self.point_queue

    def Process(self, *, target, args):
        self.process_target = target
        self.process_args = args
        return self.process


def _overlay_with_fake_context(
    monkeypatch, messages=(("ready", None),), **process_kwargs
):
    control = FakeControl(messages)
    process = FakeProcess(control, **process_kwargs)
    context = FakeContext(control, process)
    monkeypatch.setattr(
        overlay_module.multiprocessing,
        "get_context",
        lambda method: context if method == "spawn" else pytest.fail(method),
    )
    return GazeOverlay(), context


def test_start_uses_spawn_and_waits_for_exact_ready_handshake(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)

    overlay.start()

    assert context.process.started is True
    assert context.pipe_duplex is True
    assert context.queue_maxsize == 1
    assert context.process_target is overlay_module._overlay_process_main
    assert context.child_control.closed is True


def test_child_entrypoint_transfers_a_formatted_traceback(monkeypatch):
    control = FakeControl()
    source_error = RuntimeError("child paint failed")

    def fail_before_ready(control_connection, point_queue, config):
        raise source_error

    monkeypatch.setattr(
        overlay_module, "_run_qt_overlay", fail_before_ready
    )

    point_queue = SimpleNamespace(close=lambda: None)

    overlay_module._overlay_process_main(control, point_queue, {})

    assert len(control.sent) == 1
    message_type, formatted_traceback = control.sent[0]
    assert message_type == "error"
    assert "Traceback (most recent call last)" in formatted_traceback
    assert "RuntimeError: child paint failed" in formatted_traceback


def test_raise_if_failed_exposes_the_child_traceback(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)
    overlay.start()
    context.control.messages.append(
        (
            "error",
            "Traceback (most recent call last):\n"
            "RuntimeError: timer callback failed\n",
        )
    )

    with pytest.raises(RuntimeError) as caught:
        overlay.raise_if_failed()

    assert context.process.terminated is True
    assert "Traceback (most recent call last)" in str(caught.value)
    assert "RuntimeError: timer callback failed" in str(caught.value)


def test_raise_if_failed_reports_unexpected_child_death(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)
    overlay.start()
    context.process.alive = False
    context.process.exitcode = 9

    with pytest.raises(
        RuntimeError, match="gaze overlay child exited unexpectedly.*9"
    ):
        overlay.raise_if_failed()


def test_update_coalesces_to_the_latest_unsent_coordinate(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)
    overlay.start()

    overlay.update_gaze_position(10, 20)
    overlay.update_gaze_position(30.9, 40.1)

    assert context.point_queue.get_nowait() == (30, 40)
    with pytest.raises(queue.Empty):
        context.point_queue.get_nowait()
    assert context.control.sent == []


def test_stop_sends_exact_control_message_and_waits_for_ack_and_exit(
    monkeypatch,
):
    overlay, context = _overlay_with_fake_context(
        monkeypatch,
        messages=(("ready", None),),
        exit_on_join=True,
    )
    context.control.reply_to_stop = True
    overlay.start()

    overlay.stop()

    assert context.control.sent == [("stop", None)]
    assert context.process.join_timeouts
    assert context.process.terminated is False


def test_stop_timeout_raises_and_terminates_the_stuck_child(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)
    monkeypatch.setattr(overlay_module, "_STOP_TIMEOUT_SECONDS", 0.01)
    overlay.start()

    with pytest.raises(
        TimeoutError, match="did not acknowledge stop within 5 seconds"
    ):
        overlay.stop()

    assert context.control.sent == [("stop", None)]
    assert context.process.terminated is True


def test_local_process_start_error_identity_is_preserved(monkeypatch):
    source_error = OSError("spawn failed")
    overlay, _ = _overlay_with_fake_context(
        monkeypatch, start_error=source_error
    )

    with pytest.raises(OSError) as caught:
        overlay.start()

    assert caught.value is source_error


def test_local_stop_send_error_identity_is_preserved(monkeypatch):
    overlay, context = _overlay_with_fake_context(monkeypatch)
    overlay.start()
    source_error = BrokenPipeError("control pipe failed")
    context.control.send_error = source_error

    with pytest.raises(BrokenPipeError) as caught:
        overlay.stop()

    assert caught.value is source_error


def test_linux_selector_never_live_imports_win32(monkeypatch):
    selector_name = "my_model_arch.cpu_fast.gaze_overlay"
    sys.modules.pop(selector_name, None)
    requested_modules = []
    real_import = builtins.__import__

    def reject_win32(name, globals=None, locals=None, fromlist=(), level=0):
        if name.endswith("gaze_show_utils") or name.startswith("win32"):
            requested_modules.append(name)
            raise AssertionError(f"unexpected Win32 import: {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(builtins, "__import__", reject_win32)

    selector = importlib.import_module(selector_name)

    assert selector.GazeOverlay is GazeOverlay
    assert requested_modules == []


def test_selector_uses_existing_win32_overlay_only_on_win32(monkeypatch):
    selector_name = "my_model_arch.cpu_fast.gaze_overlay"
    win32_module_name = "my_model_arch.cpu_fast.gaze_show_utils"
    sys.modules.pop(selector_name, None)
    win32_overlay = object()
    fake_win32_module = ModuleType(win32_module_name)
    fake_win32_module.GazeOverlay = win32_overlay
    monkeypatch.setitem(sys.modules, win32_module_name, fake_win32_module)
    monkeypatch.setattr(sys, "platform", "win32")

    selector = importlib.import_module(selector_name)

    assert selector.GazeOverlay is win32_overlay


def test_selector_rejects_unsupported_platform(monkeypatch):
    selector_name = "my_model_arch.cpu_fast.gaze_overlay"
    sys.modules.pop(selector_name, None)
    monkeypatch.setattr(sys, "platform", "darwin")

    with pytest.raises(
        RuntimeError, match="unsupported gaze overlay platform: darwin"
    ):
        importlib.import_module(selector_name)


def test_real_action_starts_overlay_without_a_parent_gaze_thread(monkeypatch):
    calls = []

    class FakeOverlay:
        def __init__(self, **config):
            calls.append(("init", config))

        def start(self):
            calls.append(("start", None))

    fake_selector = ModuleType("my_model_arch.cpu_fast.gaze_overlay")
    fake_selector.GazeOverlay = FakeOverlay
    monkeypatch.setitem(
        sys.modules, "my_model_arch.cpu_fast.gaze_overlay", fake_selector
    )
    pipeline = object.__new__(RealAction)
    pipeline.gaze_config = {"point_radius": 17}
    pipeline.gaze_overlay = None
    pipeline.show_gaze = False

    pipeline.start_gaze_display()

    assert calls == [
        ("init", {"point_radius": 17}),
        ("start", None),
    ]
    assert pipeline.show_gaze is True
    assert not hasattr(pipeline, "gaze_thread")
    assert not hasattr(pipeline, "gaze_running")


def test_real_action_publishes_current_gaze_and_checks_overlay_failure(
    monkeypatch,
):
    calls = []
    pipeline = object.__new__(RealAction)
    pipeline.predicted_position = (123.9, 456.1)
    pipeline.mouse_dict = None
    pipeline.key_control = False
    pipeline.wheel = SimpleNamespace(
        raise_if_failed=lambda: calls.append("wheel.raise_if_failed")
    )
    pipeline.gaze_mouse_controller = SimpleNamespace(
        raise_if_failed=lambda: calls.append("controller.raise_if_failed")
    )
    pipeline.gaze_overlay = SimpleNamespace(
        update_gaze_position=lambda x, y: calls.append(
            ("overlay.update", x, y)
        ),
        raise_if_failed=lambda: calls.append("overlay.raise_if_failed"),
    )
    pipeline.decode = lambda: calls.append("decode")
    pipeline._drain_actions = lambda: calls.append("drain_actions")
    monkeypatch.setattr(
        BindKeys,
        "call_after_each_eval_loop",
        lambda self: calls.append("inherited"),
    )

    pipeline.call_after_each_eval_loop()

    assert calls == [
        "wheel.raise_if_failed",
        "controller.raise_if_failed",
        "inherited",
        ("overlay.update", 123, 456),
        "overlay.raise_if_failed",
        "decode",
        "drain_actions",
    ]


def test_real_action_stop_keeps_failed_overlay_observable():
    source_error = RuntimeError("overlay stop failed")

    class FailingOverlay:
        def stop(self):
            raise source_error

    overlay = FailingOverlay()
    pipeline = object.__new__(RealAction)
    pipeline.gaze_overlay = overlay

    with pytest.raises(RuntimeError) as caught:
        pipeline._stop_gaze_display()

    assert caught.value is source_error
    assert pipeline.gaze_overlay is overlay


def test_production_removes_parent_gaze_thread_state_and_adds_win32_check():
    pipeline_source = Path(pipeline_module.__file__).read_text()
    win32_source_path = (
        Path(pipeline_module.__file__).with_name("gaze_show_utils.py")
    )
    win32_tree = ast.parse(win32_source_path.read_text())
    overlay_class = next(
        node
        for node in win32_tree.body
        if isinstance(node, ast.ClassDef) and node.name == "GazeOverlay"
    )
    method_names = {
        node.name
        for node in overlay_class.body
        if isinstance(node, ast.FunctionDef)
    }

    assert "gaze_thread" not in pipeline_source
    assert "gaze_running" not in pipeline_source
    assert "raise_if_failed" in method_names
