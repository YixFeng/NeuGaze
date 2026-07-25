import io
import stat
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
            "camera_width": 1280,
            "camera_height": 720,
            "camera_fps": 30,
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


def test_build_checks_wires_the_complete_diagnostic(monkeypatch, tmp_path):
    config = valid_config()
    config_path = tmp_path / "cpu.yaml"
    config_path.write_text("unused")
    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr(
        runtime.platform,
        "freedesktop_os_release",
        lambda: {"ID": "ubuntu", "VERSION_ID": "24.04"},
    )
    monkeypatch.setattr(runtime.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(
        runtime,
        "_check_x11_display",
        lambda display: f"connected to {display}",
    )
    monkeypatch.setattr(
        runtime,
        "_query_x11_extensions",
        lambda display: {"XTEST", "XFIXES"},
    )
    monkeypatch.setattr(
        runtime,
        "_compositor_owner_exists",
        lambda display: False,
    )
    monkeypatch.setattr(runtime, "_load_config", lambda path: config)
    monkeypatch.setattr(
        runtime,
        "check_model_assets",
        lambda loaded, root: "assets ready",
    )
    monkeypatch.setattr(
        runtime,
        "_check_orbbec_abi_host",
        lambda: "ABI ready",
    )
    monkeypatch.setattr(
        runtime,
        "check_camera_selection",
        lambda loaded, platform_name: "camera ready",
    )
    output = io.StringIO()

    failures = runtime.execute_checks(
        runtime.build_checks(config_path, require_overlay=False),
        output,
    )

    assert failures == []
    pass_names = [
        line.removeprefix("[PASS] ").split(":", 1)[0]
        for line in output.getvalue().splitlines()
        if line.startswith("[PASS] ")
    ]
    assert pass_names == [
        "Python",
        "Platform",
        "Xorg session",
        "X11 display",
        "XTest",
        "XFixes",
        "X11 compositor",
        "Configuration",
        "Model assets",
        "Orbbec binding/SDK ABI",
        "Selected camera",
    ]


def test_python_check_rejects_wrong_minor_version():
    with pytest.raises(
        RuntimeError,
        match=r"requires Python 3\.11, got 3\.12\.1",
    ):
        runtime.check_python((3, 12, 1))


@pytest.mark.parametrize(
    ("os_release", "machine", "expected"),
    (
        ({"ID": "debian", "VERSION_ID": "24.04"}, "x86_64", "requires Ubuntu 24.04"),
        ({"ID": "ubuntu", "VERSION_ID": "22.04"}, "x86_64", "requires Ubuntu 24.04"),
        ({"ID": "ubuntu", "VERSION_ID": "24.04"}, "aarch64", "requires x86_64"),
    ),
)
def test_platform_check_rejects_wrong_distribution_version_or_architecture(
    os_release,
    machine,
    expected,
):
    with pytest.raises(RuntimeError, match=expected):
        runtime.check_platform("linux", os_release, machine)


def test_platform_check_accepts_ubuntu_2404_x86_64():
    detail = runtime.check_platform(
        "linux",
        {"ID": "ubuntu", "VERSION_ID": "24.04"},
        "x86_64",
    )

    assert detail.startswith("Ubuntu 24.04 x86_64")


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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("camera_width", 0),
        ("camera_height", True),
        ("camera_fps", -1),
    ),
)
def test_camera_config_rejects_invalid_stream_values(field, value):
    config = valid_config()
    config["integrated_config"][field] = value

    with pytest.raises(
        RuntimeError,
        match=rf"integrated_config\.{field} must be a positive integer",
    ):
        runtime._camera_config(config)


def test_camera_config_rejects_missing_stream_value():
    config = valid_config()
    del config["integrated_config"]["camera_height"]

    with pytest.raises(
        RuntimeError,
        match=r"integrated_config\.camera_height must be a positive integer",
    ):
        runtime._camera_config(config)


def test_orbbec_selection_requires_approved_stream_profile():
    config = valid_config()
    config["integrated_config"]["camera_fps"] = 60

    with pytest.raises(
        RuntimeError,
        match="Gemini 335 requires 1280x720 at 30 FPS",
    ):
        runtime.check_camera_selection(
            config,
            platform_name="linux",
            orbbec_devices=[
                {"index": 0, "name": "Gemini 335", "serial": "A"}
            ],
        )


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


def test_camera_selection_rejects_regular_file_as_v4l2_device(tmp_path):
    config = valid_config()
    config["integrated_config"]["camera_backend"]["linux"] = "opencv"
    selected = tmp_path / "video0"
    selected.write_bytes(b"not a device")

    with pytest.raises(RuntimeError, match="is not a character device"):
        runtime.check_camera_selection(
            config,
            platform_name="linux",
            device_root=tmp_path,
        )


def test_camera_selection_rejects_inaccessible_v4l2_character_device(tmp_path):
    config = valid_config()
    config["integrated_config"]["camera_backend"]["linux"] = "opencv"
    char_stat = SimpleNamespace(st_mode=stat.S_IFCHR | 0o660)

    with pytest.raises(RuntimeError, match="is not accessible for read/write"):
        runtime.check_camera_selection(
            config,
            platform_name="linux",
            device_root=tmp_path,
            device_stat=lambda path: char_stat,
            device_access=lambda path, mode: False,
        )


def test_camera_selection_accepts_sdk_gemini_335_model_name():
    config = valid_config()

    detail = runtime.check_camera_selection(
        config,
        platform_name="linux",
        orbbec_devices=[
            {
                "index": 0,
                "name": "Orbbec Gemini 335",
                "serial": "ABC123",
            }
        ],
    )

    assert detail.startswith("Orbbec index 0:")
    assert "Orbbec Gemini 335" in detail
    assert "ABC123" in detail
    assert "1280x720 at 30 FPS" in detail


def test_camera_selection_rejects_non_gemini_335_orbbec_model():
    config = valid_config()

    with pytest.raises(RuntimeError, match="must be Gemini 335"):
        runtime.check_camera_selection(
            config,
            platform_name="linux",
            orbbec_devices=[
                {"index": 0, "name": "Femto Bolt", "serial": "A"}
            ],
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


def test_orbbec_probe_reports_subprocess_failure_with_output():
    def failed_process(command, **options):
        return SimpleNamespace(
            returncode=7,
            stdout="probe stdout",
            stderr="SDK stderr",
        )

    with pytest.raises(RuntimeError) as captured:
        runtime.query_orbbec_devices(run_command=failed_process)

    message = str(captured.value)
    assert "exited 7" in message
    assert "probe stdout" in message
    assert "SDK stderr" in message


def test_orbbec_probe_preserves_primary_failure_when_cleanup_also_fails(tmp_path):
    probe_directory = tmp_path / "probe"
    probe_directory.mkdir()

    class CleanupFails:
        name = str(probe_directory)

        def cleanup(self):
            raise OSError("cleanup failed")

    def failed_process(command, **options):
        return SimpleNamespace(
            returncode=9,
            stdout="primary stdout",
            stderr="primary stderr",
        )

    with pytest.raises(RuntimeError) as captured:
        runtime.query_orbbec_devices(
            run_command=failed_process,
            temporary_directory_factory=lambda **options: CleanupFails(),
        )

    assert "exited 9" in str(captured.value)
    assert "primary stdout" in str(captured.value)
    assert "primary stderr" in str(captured.value)
    assert any(
        "cleanup failed" in note
        for note in getattr(captured.value, "__notes__", ())
    )


def test_ldd_orbbec_library_reports_unresolved_dependency(tmp_path):
    extension = tmp_path / "pyorbbecsdk.so"

    def unresolved(command, **options):
        return SimpleNamespace(
            returncode=0,
            stdout="\tlibOrbbecSDK.so.2 => not found\n",
            stderr="loader diagnostics",
        )

    with pytest.raises(RuntimeError) as captured:
        runtime._ldd_orbbec_library(extension, run_command=unresolved)

    message = str(captured.value)
    assert "libOrbbecSDK was not found" in message
    assert "ldd" in message
    assert "not found" in message
    assert "loader diagnostics" in message


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
