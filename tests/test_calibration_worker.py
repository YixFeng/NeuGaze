import io
import json
from pathlib import Path

import pytest
import yaml

from my_model_arch.cpu_fast import calibration_worker as worker


def write_model(root, calibration_time="20260727_120000"):
    path = root / "model_weights" / calibration_time / "model.pkl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"model")
    return path


def result_line(calibration_time="20260727_120000", model_path=None):
    if model_path is None:
        model_path = f"model_weights/{calibration_time}/model.pkl"
    return worker.RESULT_PREFIX + json.dumps(
        {
            "calibration_time": calibration_time,
            "model_path": model_path,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def test_parse_calibration_result_accepts_one_exact_existing_model(tmp_path):
    model = write_model(tmp_path)
    stdout = b"training log\n" + result_line() + b"\n"

    assert worker.parse_calibration_result(stdout, tmp_path) == (
        "20260727_120000",
        model.relative_to(tmp_path).as_posix(),
    )


@pytest.mark.parametrize(
    ("stdout", "exception"),
    [
        (b"training log\n", RuntimeError),
        (result_line() + b"\n" + result_line(), RuntimeError),
        (worker.RESULT_PREFIX + b"\xff", UnicodeDecodeError),
        (worker.RESULT_PREFIX + b"not json", json.JSONDecodeError),
        (
            worker.RESULT_PREFIX
            + b'{"calibration_time":"20260727_120000"}',
            ValueError,
        ),
        (
            worker.RESULT_PREFIX
            + b'{"calibration_time":"20260727_120000",'
            + b'"model_path":"model_weights/20260727_120000/model.pkl",'
            + b'"extra":true}',
            ValueError,
        ),
        (
            worker.RESULT_PREFIX
            + b'{"calibration_time":1,'
            + b'"model_path":"model_weights/20260727_120000/model.pkl"}',
            TypeError,
        ),
        (
            worker.RESULT_PREFIX
            + b'{"calibration_time":"2026-07-27",'
            + b'"model_path":"model_weights/2026-07-27/model.pkl"}',
            ValueError,
        ),
        (
            result_line(
                model_path="model_weights/20260727_120001/model.pkl"
            ),
            ValueError,
        ),
        (result_line(model_path="/tmp/model.pkl"), ValueError),
        (result_line(model_path="../model.pkl"), ValueError),
        (
            result_line(model_path="model_weights/20260727_120000/not-model.pkl"),
            ValueError,
        ),
    ],
)
def test_parse_calibration_result_rejects_invalid_protocol(
    tmp_path, stdout, exception
):
    write_model(tmp_path)

    with pytest.raises(exception):
        worker.parse_calibration_result(stdout, tmp_path)


def test_parse_calibration_result_requires_existing_model(tmp_path):
    with pytest.raises(FileNotFoundError):
        worker.parse_calibration_result(result_line(), tmp_path)


def write_config(path):
    config = {
        "real_action_config": {"show_gaze": False},
        "gaze_config": {"point_radius": 50},
        "mouse_control_config": {"dead_zone": 250},
        "wheel_config": {"radius": 1000},
        "key_config": {"left_click": "left_click"},
        "robot_wheel_config": {"radius": 400},
        "robot_action_config": {"actions": {}, "expressions": {}},
        "head_angles_center": {"yaw": 0.0},
        "head_angles_scale": {"yaw": 88.0},
        "expression_evaluator_config": {"expressions": {}},
        "integrated_config": {
            "camera_width": 1280,
            "camera_height": 720,
            "camera_fps": 30,
        },
    }
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config


class FakePipeline:
    def __init__(
        self,
        events,
        calibration_time="20260727_120000",
        completed=True,
        start_error=None,
        quit_error=None,
    ):
        self.events = events
        self.calibration_time = calibration_time
        self.completed = completed
        self.start_error = start_error
        self.quit_error = quit_error
        self.quit = False

    def start_calibration(self):
        self.events.append("pipeline.start")
        if self.start_error is not None:
            raise self.start_error
        return self.completed

    def quit_pipeline(self):
        self.events.append("pipeline.quit")
        self.quit = True
        if self.quit_error is not None:
            raise self.quit_error


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    events = []
    config_path = tmp_path / "cpu.yaml"
    config = write_config(config_path)
    monkeypatch.setattr(
        worker.desktop, "initialize", lambda: events.append("desktop.init")
    )
    monkeypatch.setattr(
        worker.desktop, "close", lambda: events.append("desktop.close")
    )
    return tmp_path, config_path, config, events, monkeypatch


def test_run_calibration_cleans_pipeline_and_desktop_before_result(lifecycle):
    root, config_path, config, events, monkeypatch = lifecycle

    class RecordingOutput(io.BytesIO):
        def write(self, data):
            events.append("result.write")
            return super().write(data)

    output = RecordingOutput()
    model = write_model(root)
    pipeline = FakePipeline(events)
    created_with = []
    monkeypatch.setattr(
        worker,
        "RealAction",
        lambda **kwargs: created_with.append(kwargs) or pipeline,
    )

    result = worker.run_calibration(config_path, output, repository_root=root)

    assert result == ("20260727_120000", model.relative_to(root).as_posix())
    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
        "result.write",
    ]
    assert created_with == [
        {
            **config["real_action_config"],
            "gaze_config": config["gaze_config"],
            "mouse_control_config": config["mouse_control_config"],
            "wheel_config": config["wheel_config"],
            "configuration": config["key_config"],
            "robot_wheel_config": config["robot_wheel_config"],
            "robot_action_config": config["robot_action_config"],
            "head_angles_center": config["head_angles_center"],
            "head_angles_scale": config["head_angles_scale"],
            "expression_evaluator_config": config[
                "expression_evaluator_config"
            ],
            **config["integrated_config"],
        }
    ]
    assert output.getvalue() == result_line() + b"\n"


def test_run_calibration_cleans_desktop_when_pipeline_construction_fails(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    error = RuntimeError("construction failed")
    monkeypatch.setattr(
        worker, "RealAction", lambda **kwargs: (_ for _ in ()).throw(error)
    )

    with pytest.raises(RuntimeError) as raised:
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert raised.value is error
    assert events == ["desktop.init", "desktop.close"]


def test_run_calibration_keeps_primary_error_and_notes_cleanup_failures(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    primary = RuntimeError("calibration failed")
    pipeline = FakePipeline(events, start_error=primary, quit_error=OSError("quit"))
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    def close():
        events.append("desktop.close")
        raise OSError("desktop")

    monkeypatch.setattr(worker.desktop, "close", close)

    with pytest.raises(RuntimeError) as raised:
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert raised.value is primary
    assert list(raised.value.__notes__) == [
        "pipeline cleanup also failed: OSError('quit')",
        "desktop cleanup also failed: OSError('desktop')",
    ]
    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_cleanup_failure_is_raised(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    pipeline = FakePipeline(events, quit_error=OSError("quit"))
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    with pytest.raises(OSError, match="quit"):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_desktop_cleanup_failure_is_raised(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    write_model(root)
    pipeline = FakePipeline(events)
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    def close():
        events.append("desktop.close")
        raise OSError("desktop")

    monkeypatch.setattr(worker.desktop, "close", close)

    with pytest.raises(OSError, match="desktop"):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_rejects_cancelled_calibration(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    pipeline = FakePipeline(events, completed=None)
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    with pytest.raises(RuntimeError, match="calibration did not complete"):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


@pytest.mark.parametrize("calibration_time", [None, "not-a-timestamp"])
def test_run_calibration_rejects_invalid_calibration_time(
    lifecycle, calibration_time
):
    root, config_path, _, events, monkeypatch = lifecycle
    pipeline = FakePipeline(events, calibration_time=calibration_time)
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    with pytest.raises((TypeError, ValueError)):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_rejects_missing_calibration_time(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    pipeline = FakePipeline(events)
    del pipeline.calibration_time
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    with pytest.raises(AttributeError):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_rejects_missing_model(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    pipeline = FakePipeline(events)
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    with pytest.raises(FileNotFoundError):
        worker.run_calibration(config_path, io.BytesIO(), repository_root=root)

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
    ]


def test_run_calibration_propagates_output_write_failure_after_cleanup(lifecycle):
    root, config_path, _, events, monkeypatch = lifecycle
    write_model(root)
    pipeline = FakePipeline(events)
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)

    class BrokenOutput(io.BytesIO):
        def write(self, data):
            events.append("result.write")
            raise OSError("write")

    with pytest.raises(OSError, match="write"):
        worker.run_calibration(
            config_path, BrokenOutput(), repository_root=root
        )

    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
        "result.write",
    ]
