import signal
import threading
from types import SimpleNamespace

import pytest

from my_model_arch.cpu_fast import evaluation_worker


def _install_worker_fakes(monkeypatch, pipeline, events):
    active_handlers = {}
    restored_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    signal_calls = []

    def set_signal(signum, handler):
        signal_calls.append((signum, handler))
        if callable(handler):
            active_handlers[signum] = handler

    monkeypatch.setattr(
        evaluation_worker.signal,
        "getsignal",
        lambda signum: restored_handlers[signum],
    )
    monkeypatch.setattr(evaluation_worker.signal, "signal", set_signal)
    monkeypatch.setattr(
        evaluation_worker,
        "load_config",
        lambda path: {"config_path": path},
    )
    monkeypatch.setattr(
        evaluation_worker,
        "build_pipeline",
        lambda config: pipeline,
    )
    monkeypatch.setattr(
        evaluation_worker.desktop,
        "initialize",
        lambda: events.append("desktop.initialize"),
    )
    monkeypatch.setattr(
        evaluation_worker.desktop,
        "close",
        lambda: events.append("desktop.close"),
    )
    return active_handlers, restored_handlers, signal_calls


def test_evaluation_worker_runs_and_cleans_resources(monkeypatch, tmp_path):
    events = []
    pipeline = SimpleNamespace(quit=False)

    def start_evaluation():
        events.append(
            ("pipeline.start_evaluation", threading.current_thread().name)
        )

    def quit_pipeline():
        events.append("pipeline.quit_pipeline")
        pipeline.quit = True

    pipeline.start_evaluation = start_evaluation
    pipeline.quit_pipeline = quit_pipeline
    _, restored_handlers, signal_calls = _install_worker_fakes(
        monkeypatch, pipeline, events
    )

    evaluation_worker.run_evaluation(tmp_path / "cpu.yaml")

    assert events == [
        "desktop.initialize",
        ("pipeline.start_evaluation", "neugaze-evaluation"),
        "pipeline.quit_pipeline",
        "desktop.close",
    ]
    assert signal_calls[-2:] == [
        (signal.SIGINT, restored_handlers[signal.SIGINT]),
        (signal.SIGTERM, restored_handlers[signal.SIGTERM]),
    ]


def test_sigterm_requests_one_pipeline_cleanup(monkeypatch, tmp_path):
    events = []
    pipeline = SimpleNamespace(quit=False)
    active_handlers = None
    evaluation_started = threading.Event()
    allow_evaluation_return = threading.Event()

    def start_evaluation():
        events.append("pipeline.start_evaluation")
        evaluation_started.set()
        assert allow_evaluation_return.wait(2)
        events.append("pipeline.start_return")

    def request_evaluation_stop():
        events.append("pipeline.request_evaluation_stop")

    def quit_pipeline():
        events.append("pipeline.quit_pipeline")
        pipeline.quit = True

    pipeline.start_evaluation = start_evaluation
    pipeline.request_evaluation_stop = request_evaluation_stop
    pipeline.quit_pipeline = quit_pipeline
    active_handlers, _, _ = _install_worker_fakes(
        monkeypatch, pipeline, events
    )

    def send_sigterm():
        assert evaluation_started.wait(2)
        active_handlers[signal.SIGTERM](signal.SIGTERM, None)
        allow_evaluation_return.set()

    controller = threading.Thread(target=send_sigterm)
    controller.start()
    evaluation_worker.run_evaluation(tmp_path / "cpu.yaml")
    controller.join()

    assert events == [
        "desktop.initialize",
        "pipeline.start_evaluation",
        "pipeline.request_evaluation_stop",
        "pipeline.start_return",
        "pipeline.quit_pipeline",
        "desktop.close",
    ]


def test_worker_preserves_evaluation_failure_and_cleans_once(
    monkeypatch, tmp_path
):
    events = []
    error = RuntimeError("evaluation failed")
    pipeline = SimpleNamespace(quit=False)

    def start_evaluation():
        raise error

    def quit_pipeline():
        events.append("pipeline.quit_pipeline")
        pipeline.quit = True

    pipeline.start_evaluation = start_evaluation
    pipeline.quit_pipeline = quit_pipeline
    _install_worker_fakes(monkeypatch, pipeline, events)

    with pytest.raises(RuntimeError) as caught:
        evaluation_worker.run_evaluation(tmp_path / "cpu.yaml")

    assert caught.value is error
    assert events == [
        "desktop.initialize",
        "pipeline.quit_pipeline",
        "desktop.close",
    ]


def test_worker_adds_cleanup_failures_to_primary_error(
    monkeypatch, tmp_path
):
    events = []
    error = RuntimeError("evaluation failed")
    pipeline_cleanup_error = OSError("camera close failed")
    desktop_cleanup_error = OSError("X11 close failed")
    pipeline = SimpleNamespace(quit=False)

    def start_evaluation():
        raise error

    def quit_pipeline():
        raise pipeline_cleanup_error

    def close_desktop():
        raise desktop_cleanup_error

    pipeline.start_evaluation = start_evaluation
    pipeline.quit_pipeline = quit_pipeline
    _install_worker_fakes(monkeypatch, pipeline, events)
    monkeypatch.setattr(evaluation_worker.desktop, "close", close_desktop)

    with pytest.raises(RuntimeError) as caught:
        evaluation_worker.run_evaluation(tmp_path / "cpu.yaml")

    assert caught.value is error
    notes = getattr(error, "__notes__", ())
    assert any("camera close failed" in note for note in notes)
    assert any("X11 close failed" in note for note in notes)
