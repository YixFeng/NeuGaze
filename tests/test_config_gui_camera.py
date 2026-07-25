import copy
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import yaml


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QMessageBox

import config_gui_cpu as gui
from my_model_arch.cpu_fast.camera import CameraInfo


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture
def config_mapping():
    config_path = Path(gui.__file__).parent / "configs" / "cpu.yaml"
    mapping = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    mapping["unrelated_top_level"] = {"preserve": ["exactly", 7]}
    mapping["integrated_config"]["unrelated_integrated"] = {
        "future": True,
    }
    return mapping


class FakeCamera:
    def __init__(self, frame=None, events=None):
        self.frame = (
            np.zeros((720, 1280, 3), dtype=np.uint8)
            if frame is None
            else frame
        )
        self.events = events
        self.close_calls = 0

    def read(self):
        if self.events is not None:
            self.events.append("read")
        return self.frame

    def close(self):
        self.close_calls += 1
        if self.events is not None:
            self.events.append("close")


@pytest.fixture
def window_factory(app, monkeypatch, tmp_path, config_mapping):
    windows = []

    def create(
        *,
        mapping=None,
        cameras=None,
        opener=None,
        list_events=None,
    ):
        configured = copy.deepcopy(mapping or config_mapping)
        config_path = tmp_path / f"config-{len(windows)}.yaml"
        config_path.write_text(
            yaml.safe_dump(configured, sort_keys=False),
            encoding="utf-8",
        )
        original_load = gui.ConfigWindow.load_config

        def load_config(window, _config_path=None):
            return original_load(window, config_path)

        available = cameras
        if available is None:
            available = [
                CameraInfo("orbbec", 0, "Gemini 335 SN123", "SN123"),
                CameraInfo("opencv", 7, "/dev/video7"),
            ]

        def enumerate_cameras(backend, platform):
            if list_events is not None:
                list_events.append(f"list:{backend}:{platform}")
            return [camera for camera in available if camera.backend == backend]

        monkeypatch.setattr(gui.ConfigWindow, "load_config", load_config)
        monkeypatch.setattr(
            gui,
            "list_cameras",
            enumerate_cameras,
            raising=False,
        )
        monkeypatch.setattr(
            gui,
            "open_camera",
            opener or (lambda config, platform: FakeCamera()),
            raising=False,
        )
        monkeypatch.setattr(QMessageBox, "information", lambda *args: None)
        monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)

        window = gui.ConfigWindow()
        window.hotkey_timer.stop()
        window.preview_timer.stop()
        windows.append(window)
        return window, config_path

    yield create

    for window in windows:
        window.hotkey_timer.stop()
        window.preview_timer.stop()
        if getattr(window, "camera", None) is not None:
            window.camera.close()
            window.camera = None
        window.pipeline = None
        window.close()
        window.deleteLater()
    app.processEvents()


def combo_index(combo, data):
    for index in range(combo.count()):
        if combo.itemData(index) == data:
            return index
    raise AssertionError(f"{data!r} is not present in combo")


def test_linux_backend_combo_defaults_to_yaml_orbbec(window_factory):
    window, _ = window_factory()

    assert window.camera_backend_combo.currentData() == "orbbec"
    assert window.camera_config.backend == "orbbec"
    assert window.camera_config.device_id == 0


def test_switching_backend_closes_preview_before_enumeration(window_factory):
    events = []
    window, _ = window_factory(list_events=events)
    window.camera = FakeCamera(events=events)
    events.clear()

    window.camera_backend_combo.setCurrentIndex(
        combo_index(window.camera_backend_combo, "opencv")
    )

    assert events[:2] == ["close", "list:opencv:linux"]
    assert window.camera is None


def test_device_combo_keeps_backend_and_device_id_in_item_data(window_factory):
    window, _ = window_factory()

    orbbec_index = combo_index(window.camera_combo, ("orbbec", 0))
    assert window.camera_combo.itemText(orbbec_index) == "Gemini 335 SN123"

    window.camera_backend_combo.setCurrentIndex(
        combo_index(window.camera_backend_combo, "opencv")
    )
    opencv_index = combo_index(window.camera_combo, ("opencv", 7))
    assert window.camera_combo.itemText(opencv_index) == "/dev/video7"


def test_preview_renders_supplied_contiguous_bgr_frame_directly(window_factory):
    frame = np.array(
        [[[0, 0, 255], [255, 0, 0]]],
        dtype=np.uint8,
    )
    assert frame.flags.c_contiguous
    window, _ = window_factory()
    window.preview_label.setMinimumSize(QSize(0, 0))
    window.preview_label.setFixedSize(2, 1)
    window.camera = FakeCamera(frame)

    window.update_preview()

    image = window.preview_label.pixmap().toImage()
    assert (image.width(), image.height()) == (2, 1)
    assert image.pixelColor(0, 0).getRgb()[:3] == (255, 0, 0)
    assert image.pixelColor(1, 0).getRgb()[:3] == (0, 0, 255)


def test_backend_enumeration_error_is_visible_after_preview_close(
    window_factory, monkeypatch
):
    events = []
    window, _ = window_factory(list_events=events)
    window.camera = FakeCamera(events=events)
    events.clear()
    error = RuntimeError("udev enumeration failed")
    messages = []

    def fail_enumeration(backend, platform):
        events.append(f"list:{backend}:{platform}")
        raise error

    monkeypatch.setattr(gui, "list_cameras", fail_enumeration)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    with pytest.raises(RuntimeError) as caught:
        window.on_camera_backend_changed(
            combo_index(window.camera_backend_combo, "opencv")
        )

    assert caught.value is error
    assert events[:2] == ["close", "list:opencv:linux"]
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "RuntimeError: udev enumeration failed" in messages[0][1]
    assert window.camera is None
    assert window.camera_combo.count() == 1
    assert window.camera_combo.currentData() is None
    assert not window.camera_combo.isEnabled()
    assert not window.calibrate_btn.isEnabled()
    assert not window.evaluate_btn.isEnabled()


def test_camera_close_failure_is_not_retried_before_opening_new_source(
    window_factory, monkeypatch
):
    window, _ = window_factory()
    error = RuntimeError("preview close failed")
    messages = []
    open_calls = []

    class CloseFailureCamera:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1
            raise error

    camera = CloseFailureCamera()
    window.camera = camera
    monkeypatch.setattr(
        gui,
        "open_camera",
        lambda config, platform: open_calls.append((config, platform)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    with pytest.raises(RuntimeError) as caught:
        window.on_camera_selected(
            combo_index(window.camera_combo, ("orbbec", 0))
        )

    retained_camera = window.camera
    window.camera = None
    assert caught.value is error
    assert camera.close_calls == 1
    assert retained_camera is camera
    assert open_calls == []
    assert len(messages) == 1
    assert "RuntimeError: preview close failed" in messages[0][1]


def test_backend_switch_invalidates_devices_before_preview_close_failure(
    window_factory, monkeypatch
):
    list_calls = []
    open_calls = []
    window, _ = window_factory(list_events=list_calls)
    error = RuntimeError("preview close blocked backend switch")
    messages = []

    close_states = []

    class CloseFailureCamera:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1
            close_states.append(
                (
                    window.camera_combo.count(),
                    window.camera_combo.currentData(),
                    window.camera_combo.isEnabled(),
                )
            )
            raise error

    device_signal_events = []
    window.camera_combo.currentIndexChanged.connect(device_signal_events.append)
    camera = CloseFailureCamera()
    window.camera = camera
    list_calls.clear()
    monkeypatch.setattr(
        gui,
        "open_camera",
        lambda config, platform: open_calls.append((config, platform)),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    with pytest.raises(RuntimeError) as caught:
        window.on_camera_backend_changed(
            combo_index(window.camera_backend_combo, "opencv")
        )

    retained_camera = window.camera
    window.camera = None
    assert caught.value is error
    assert camera.close_calls == 1
    assert retained_camera is camera
    assert close_states == [(1, None, False)]
    assert device_signal_events == []
    assert list_calls == []
    assert open_calls == []
    assert window.camera_combo.count() == 1
    assert window.camera_combo.currentData() is None
    assert not window.camera_combo.isEnabled()
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "RuntimeError: preview close blocked backend switch" in messages[0][1]


def test_camera_open_error_is_visible_and_preserves_exception(
    window_factory, monkeypatch
):
    window, _ = window_factory()
    error = RuntimeError("Orbbec RGB stream failed")
    calls = []
    messages = []

    def fail_open(config, platform):
        calls.append((config.backend, config.device_id, platform))
        raise error

    monkeypatch.setattr(gui, "open_camera", fail_open)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    with pytest.raises(RuntimeError) as caught:
        window.on_camera_selected(
            combo_index(window.camera_combo, ("orbbec", 0))
        )

    assert caught.value is error
    assert calls == [("orbbec", 0, "linux")]
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "RuntimeError: Orbbec RGB stream failed" in messages[0][1]
    assert window.camera is None
    assert not window.camera_confirm_btn.isEnabled()
    assert not window.calibrate_btn.isEnabled()
    assert not window.evaluate_btn.isEnabled()


def test_camera_read_error_is_visible_and_preserves_exception(
    window_factory, monkeypatch
):
    window, _ = window_factory()
    error = TimeoutError("RGB frame timed out")
    messages = []

    class FailingCamera:
        def read(self):
            raise error

        def close(self):
            raise AssertionError("read failure must not silently switch cameras")

    window.camera = FailingCamera()
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    with pytest.raises(TimeoutError) as caught:
        window.update_preview()

    assert caught.value is error
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "TimeoutError: RGB frame timed out" in messages[0][1]
    assert "camera cleanup after failure also failed" in messages[0][1]
    assert "AssertionError" in messages[0][1]
    assert window.camera is None
    assert not window.camera_confirm_btn.isEnabled()
    assert not window.calibrate_btn.isEnabled()
    assert not window.evaluate_btn.isEnabled()


def test_pipeline_initialization_error_is_shown_once_and_re_raised(
    window_factory, monkeypatch
):
    window, _ = window_factory()
    error = RuntimeError("pipeline camera open failed")
    messages = []

    def fail_pipeline(**kwargs):
        raise error

    monkeypatch.setitem(
        sys.modules,
        "my_model_arch.cpu_fast.pipeline",
        SimpleNamespace(RealAction=fail_pipeline),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )
    window.calibrate_btn.setEnabled(True)
    window.evaluate_btn.setEnabled(True)

    with pytest.raises(RuntimeError) as caught:
        window.initialize_pipeline()

    assert caught.value is error
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "RuntimeError: pipeline camera open failed" in messages[0][1]
    assert window.pipeline is None
    assert not window.calibrate_btn.isEnabled()
    assert not window.evaluate_btn.isEnabled()


@pytest.mark.parametrize(
    ("entrypoint", "pipeline_event"),
    [
        ("start_calibration", "pipeline.calibrate"),
        ("start_evaluation", "pipeline.evaluate"),
    ],
)
def test_pipeline_camera_ownership_starts_after_preview_close(
    window_factory, entrypoint, pipeline_event
):
    events = []
    window, _ = window_factory()
    window.camera = FakeCamera(events=events)
    window.pipeline = SimpleNamespace(
        start_calibration=lambda: events.append("pipeline.calibrate"),
        start_evaluation=lambda: events.append("pipeline.evaluate"),
    )

    getattr(window, entrypoint)()

    assert events[:2] == ["close", pipeline_event]
    assert window.camera is None



def test_confirming_new_camera_retires_pipeline_with_old_camera_config(
    window_factory
):
    events = []
    window, _ = window_factory()
    window.camera_backend_combo.setCurrentIndex(
        combo_index(window.camera_backend_combo, "opencv")
    )
    window.camera_combo.blockSignals(True)
    try:
        window.camera_combo.setCurrentIndex(
            combo_index(window.camera_combo, ("opencv", 7))
        )
    finally:
        window.camera_combo.blockSignals(False)
    window.camera = FakeCamera(events=events)
    window.pipeline = SimpleNamespace(
        quit_pipeline=lambda: events.append("pipeline.quit")
    )

    window.confirm_camera_selection()

    assert events == ["close", "pipeline.quit"]
    assert window.pipeline is None
    assert window.camera_config.backend == "opencv"
    assert window.camera_config.device_id == 7


def test_save_preserves_windows_backend_and_unrelated_yaml(
    window_factory, config_mapping, tmp_path
):
    original = copy.deepcopy(config_mapping)
    window, _ = window_factory(mapping=original)
    window.camera_backend_combo.setCurrentIndex(
        combo_index(window.camera_backend_combo, "opencv")
    )
    window.camera_combo.setCurrentIndex(
        combo_index(window.camera_combo, ("opencv", 7))
    )
    window.confirm_camera_selection()
    output_path = tmp_path / "saved.yaml"

    window.save_config_to_file(output_path)

    saved = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    integrated = saved["integrated_config"]
    assert integrated["camera_backend"] == {
        "linux": "opencv",
        "win32": "opencv",
    }
    assert integrated["cam_id"] == 7
    assert integrated["camera_width"] == 1280
    assert integrated["camera_height"] == 720
    assert integrated["camera_fps"] == 30
    assert saved["unrelated_top_level"] == original["unrelated_top_level"]
    assert (
        integrated["unrelated_integrated"]
        == original["integrated_config"]["unrelated_integrated"]
    )


def test_save_roundtrip_changes_only_camera_and_edited_hydrated_widgets(
    window_factory, config_mapping, tmp_path
):
    original = copy.deepcopy(config_mapping)
    original["gaze_config"]["future_gaze"] = {
        "sequence": [1, {"pair": [2, 3]}],
    }
    original["mouse_control_config"]["future_mouse"] = {"enabled": None}
    original["wheel_config"]["future_wheel"] = {"shape": [3, 4]}
    original["real_action_config"]["future_action"] = {"args": ["x", "y"]}
    original["integrated_config"].update(
        {
            "regression_model_path": None,
            "screen_size": [1600, 900],
            "pred_point_color": [12, 34, 56],
            "true_point_color": [78, 90, 123],
            "gaze_bias": [-321, 654],
            "future_integrated": {"nested": [True, None]},
        }
    )
    original["head_angles_center"]["future_center"] = {"axis": [1, 2]}
    original["head_angles_scale"]["future_scale"] = {"axis": [3, 4]}
    expression_config = original["expression_evaluator_config"]
    expression_config["future_expression_section"] = {"keep": [1, 2]}
    expression_config["expressions"]["numlock"]["future_expression"] = {
        "keep": [3, 4],
    }
    expression_config["expressions"]["numlock"]["conditions"][0][
        "future_condition"
    ] = {"keep": [5, 6]}
    expression_config["priority_rules"][0]["future_rule"] = {
        "keep": [7, 8],
    }
    original["key_config"]["future_mode"] = {
        "future_key": {"future": ["unchanged"]},
    }
    original["key_config"]["game"]["numlock"]["future_key"] = {
        "keep": [9, 10],
    }

    window, _ = window_factory(mapping=original)

    assert window.integrated_widgets["regression_model_path"].text() == ""
    assert [
        widget.value()
        for widget in window.integrated_widgets["screen_size"]
    ] == [1600, 900]
    assert [
        widget.value()
        for widget in window.integrated_widgets["pred_point_color"]
    ] == [12, 34, 56]
    assert [
        widget.value()
        for widget in window.integrated_widgets["true_point_color"]
    ] == [78, 90, 123]
    assert [
        widget.value()
        for widget in window.integrated_widgets["gaze_bias"]
    ] == [-321, 654]

    window.camera_backend_combo.setCurrentIndex(
        combo_index(window.camera_backend_combo, "opencv")
    )
    window.camera_combo.setCurrentIndex(
        combo_index(window.camera_combo, ("opencv", 7))
    )
    window.confirm_camera_selection()
    window.gaze_widgets["point_radius"].setValue(61)
    window.integrated_widgets["screen_size"][0].setValue(1728)
    output_path = tmp_path / "lossless-saved.yaml"

    window.save_config_to_file(output_path)

    saved = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(original)
    expected["gaze_config"]["point_radius"] = 61
    expected["integrated_config"]["screen_size"] = [1728, 900]
    expected["integrated_config"]["camera_backend"]["linux"] = "opencv"
    expected["integrated_config"]["cam_id"] = 7
    assert saved == expected

    window.integrated_widgets["regression_model_path"].setText(
        "model_weights/new/model.pkl"
    )
    window.save_config_to_file(output_path)
    saved_after_edit = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert (
        saved_after_edit["integrated_config"]["regression_model_path"]
        == "model_weights/new/model.pkl"
    )


def test_calibration_restart_error_is_shown_once_and_propagates_same_object(
    window_factory, monkeypatch
):
    window, _ = window_factory()
    error = RuntimeError("restart preview open failed")
    messages = []
    format_calls = []
    original_format_exc = gui.traceback.format_exc

    window.pipeline = SimpleNamespace()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args: QMessageBox.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: messages.append((title, text)),
    )

    def record_format_exc():
        format_calls.append(None)
        return original_format_exc()

    monkeypatch.setattr(gui.traceback, "format_exc", record_format_exc)
    monkeypatch.setattr(
        gui,
        "open_camera",
        lambda config, platform: (_ for _ in ()).throw(error),
    )

    with pytest.raises(RuntimeError) as caught:
        window.on_calibration_finished()

    assert caught.value is error
    assert len(format_calls) == 1
    assert len(messages) == 1
    assert messages[0][1].startswith("Traceback (most recent call last):")
    assert "RuntimeError: restart preview open failed" in messages[0][1]


@pytest.mark.parametrize(
    "camera_backend",
    [
        {"win32": "opencv"},
        {"linux": "unknown", "win32": "opencv"},
    ],
)
def test_loading_missing_or_unknown_platform_backend_fails(
    app, tmp_path, config_mapping, camera_backend
):
    mapping = copy.deepcopy(config_mapping)
    mapping["integrated_config"]["camera_backend"] = camera_backend
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text(
        yaml.safe_dump(mapping, sort_keys=False),
        encoding="utf-8",
    )
    target = SimpleNamespace(
        current_config_path=None,
        update_window_title=lambda: None,
    )

    with pytest.raises(ValueError):
        gui.ConfigWindow.load_config(target, config_path)


def test_hotkey_checks_delegate_to_desktop(window_factory, monkeypatch):
    window, _ = window_factory()
    calls = []
    window.pipeline = SimpleNamespace(
        quit_pipeline=lambda: calls.append("quit_pipeline")
    )
    monkeypatch.setattr(
        gui.desktop,
        "are_keys_down",
        lambda keys: calls.append(("are_keys_down", keys)) or True,
        raising=False,
    )

    window.check_hotkeys()

    assert calls == [
        ("are_keys_down", ("esc", "q")),
        "quit_pipeline",
    ]
    assert window.pipeline is None


def test_run_gui_owns_desktop_lifecycle(app, monkeypatch):
    calls = []

    class FakeWindow:
        def show(self):
            calls.append("show")

    monkeypatch.setattr(
        gui.desktop,
        "initialize",
        lambda: calls.append("desktop.initialize"),
        raising=False,
    )
    monkeypatch.setattr(
        gui.desktop,
        "close",
        lambda: calls.append("desktop.close"),
        raising=False,
    )
    monkeypatch.setattr(gui, "ConfigWindow", FakeWindow)
    monkeypatch.setattr(QApplication, "exec", lambda self: calls.append("exec") or 9)

    assert gui.run_gui(app) == 9
    assert calls == [
        "desktop.initialize",
        "show",
        "exec",
        "desktop.close",
    ]


def test_run_gui_preserves_primary_when_desktop_close_also_fails(
    app, monkeypatch
):
    primary = RuntimeError("event loop failed")
    cleanup = OSError("desktop close failed")

    class FakeWindow:
        def show(self):
            pass

    monkeypatch.setattr(gui.desktop, "initialize", lambda: None)
    monkeypatch.setattr(
        gui.desktop,
        "close",
        lambda: (_ for _ in ()).throw(cleanup),
    )
    monkeypatch.setattr(gui, "ConfigWindow", FakeWindow)
    monkeypatch.setattr(
        QApplication,
        "exec",
        lambda self: (_ for _ in ()).throw(primary),
    )

    with pytest.raises(RuntimeError) as caught:
        gui.run_gui(app)

    assert caught.value is primary
    assert any(
        "desktop.close() also failed" in note
        and "desktop close failed" in note
        for note in primary.__notes__
    )
