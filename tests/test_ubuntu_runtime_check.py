import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_ubuntu_runtime as runtime


def valid_config():
    return {
        "real_action_config": {"show_gaze": False},
        "integrated_config": {
            "weights": (
                "my_model_arch/cpu_fast/cpu_convert/"
                "mobileone_s0_224_fp16_pnnx.ncnn.param"
            ),
            "regression_model_path": None,
            "camera_backend": {
                "linux": "orbbec",
                "win32": "opencv",
            },
            "cam_id": 0,
        },
    }


def test_execute_checks_reports_success_one_line_per_check():
    output = io.StringIO()

    failures = runtime.execute_checks(
        (
            ("Python", lambda: "Python 3.11.11"),
            ("X11 display", lambda: "DISPLAY=':99' connected"),
        ),
        output,
    )

    assert failures == []
    assert output.getvalue().splitlines() == [
        "[PASS] Python: Python 3.11.11",
        "[PASS] X11 display: DISPLAY=':99' connected",
        "Diagnostic passed: 2 checks",
    ]


def test_execute_checks_collects_every_failure_and_preserves_tracebacks():
    output = io.StringIO()

    def fail_python():
        raise RuntimeError("Python mismatch")

    def fail_display():
        raise OSError("cannot connect")

    failures = runtime.execute_checks(
        (
            ("Python", fail_python),
            ("X11 display", fail_display),
        ),
        output,
    )

    assert [failure.name for failure in failures] == [
        "Python",
        "X11 display",
    ]
    assert [type(failure.error) for failure in failures] == [
        RuntimeError,
        OSError,
    ]
    report = output.getvalue()
    assert "[FAIL] Python: RuntimeError: Python mismatch" in report
    assert "[FAIL] X11 display: OSError: cannot connect" in report
    assert "Diagnostic failed with 2 failure(s):" in report
    assert "Traceback (most recent call last):" in report
    assert "in fail_python" in report
    assert "in fail_display" in report


def test_python_check_rejects_wrong_minor_version():
    with pytest.raises(
        RuntimeError,
        match=r"requires Python 3\.11, got 3\.12\.1",
    ):
        runtime.check_python((3, 12, 1))


def test_session_check_rejects_wayland_even_with_display():
    with pytest.raises(
        RuntimeError,
        match="XDG_SESSION_TYPE='wayland'.*requires Xorg",
    ):
        runtime.check_session(
            {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}
        )


def test_session_check_rejects_absent_display():
    with pytest.raises(
        RuntimeError,
        match=r"DISPLAY must name an X11 server, got None",
    ):
        runtime.check_session({"XDG_SESSION_TYPE": "x11"})


@pytest.mark.parametrize("extension", ["XTEST", "XFIXES"])
def test_x11_extension_check_rejects_each_missing_extension(extension):
    present = {"XTEST", "XFIXES"} - {extension}

    with pytest.raises(
        RuntimeError,
        match=rf"display ':99' is missing required extension {extension}",
    ):
        runtime.check_x11_extension(":99", present, extension)


def test_compositor_check_rejects_missing_owner_when_gaze_is_enabled():
    with pytest.raises(
        RuntimeError,
        match="selection _NET_WM_CM_S0 has no owner",
    ):
        runtime.check_compositor(
            config={"real_action_config": {"show_gaze": True}},
            require_overlay=False,
            owner_exists=False,
        )


def test_compositor_check_rejects_missing_owner_when_cli_requires_overlay():
    with pytest.raises(
        RuntimeError,
        match="selection _NET_WM_CM_S0 has no owner",
    ):
        runtime.check_compositor(
            config={"real_action_config": {"show_gaze": False}},
            require_overlay=True,
            owner_exists=False,
        )


def test_model_asset_check_lists_every_missing_file(tmp_path):
    config = valid_config()

    with pytest.raises(RuntimeError) as captured:
        runtime.check_model_assets(config, tmp_path)

    message = str(captured.value)
    assert "missing required model asset(s)" in message
    assert (
        "models/face_landmarker_v2_with_blendshapes.task" in message
    )
    assert (
        "mobileone_s0_224_fp16_pnnx.ncnn.param" in message
    )
    assert (
        "mobileone_s0_224_fp16_pnnx.ncnn.bin" in message
    )


def test_model_asset_check_accepts_required_and_configured_files(tmp_path):
    config = valid_config()
    weights = tmp_path / config["integrated_config"]["weights"]
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"param")
    weights.with_suffix(".bin").write_bytes(b"bin")
    face_model = (
        tmp_path / "models/face_landmarker_v2_with_blendshapes.task"
    )
    face_model.parent.mkdir()
    face_model.write_bytes(b"task")
    regression_model = tmp_path / "models/calibration.pkl"
    regression_model.write_bytes(b"pkl")
    config["integrated_config"]["regression_model_path"] = str(
        regression_model.relative_to(tmp_path)
    )

    detail = runtime.check_model_assets(config, tmp_path)

    assert detail == "4 required model assets exist"


def test_camera_selection_rejects_missing_selected_v4l2_device(tmp_path):
    config = valid_config()
    config["integrated_config"]["camera_backend"]["linux"] = "opencv"
    config["integrated_config"]["cam_id"] = 7

    with pytest.raises(
        RuntimeError,
        match=r"selected OpenCV/V4L2 camera /dev/video7 does not exist",
    ):
        runtime.check_camera_selection(
            config,
            platform_name="linux",
            device_root=tmp_path,
        )


def test_orbbec_probe_contains_sdk_files_outside_caller_cwd(
    tmp_path,
    monkeypatch,
):
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    probe_directories = []

    def sdk_process(command, **options):
        probe_directory = Path(options["cwd"])
        probe_directories.append(probe_directory)
        log_directory = probe_directory / "Log"
        log_directory.mkdir()
        (log_directory / "OrbbecSDK.log.txt").write_text("SDK log")
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "binding startup output\n"
                "NEUGAZE_ORBBEC_DEVICES={\"device_count\": 1, "
                "\"devices\": [{\"index\": 0, "
                "\"name\": \"Gemini 335\", "
                "\"serial\": \"ABC123\"}]}\n"
            ),
            stderr="",
        )

    devices = runtime.query_orbbec_devices(run_command=sdk_process)

    assert devices == [
        {"index": 0, "name": "Gemini 335", "serial": "ABC123"}
    ]
    assert list(caller.iterdir()) == []
    assert len(probe_directories) == 1
    assert not probe_directories[0].exists()


def test_orbbec_abi_check_accepts_expected_system_sdk():
    resolved = Path("/usr/local/lib/libOrbbecSDK.so.2.9.3")

    detail = runtime.check_orbbec_abi(
        binding_version="2.1.1",
        sdk_version="2.9.3",
        resolved_library=resolved,
        expected_library=resolved,
    )

    assert detail == (
        "pyorbbecsdk2=2.1.1, SDK=2.9.3, "
        "libOrbbecSDK=/usr/local/lib/libOrbbecSDK.so.2.9.3"
    )


def test_orbbec_abi_check_rejects_wheel_bundled_library_resolution():
    expected = Path("/usr/local/lib/libOrbbecSDK.so.2.9.3")
    bundled = Path(
        "/venv/lib/python3.11/site-packages/"
        "pyorbbecsdk/libOrbbecSDK.so.2.8.6"
    )

    with pytest.raises(RuntimeError) as captured:
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.8.6",
            resolved_library=bundled,
            expected_library=expected,
        )

    message = str(captured.value)
    assert "SDK version expected 2.9.3, got 2.8.6" in message
    assert f"libOrbbecSDK expected {expected}, got {bundled}" in message
    assert "pyorbbecsdk2=2.1.1" in message
