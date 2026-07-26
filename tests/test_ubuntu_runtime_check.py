import io
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from Xlib import display as xdisplay
from Xlib.ext import xinput

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
        "_check_xinput_host",
        lambda display: "XI2 ready",
        raising=False,
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
        "XInput/XI2",
        "X11 compositor",
        "Configuration",
        "Model assets",
        "Orbbec binding/SDK ABI",
        "Selected camera",
    ]
    assert "Diagnostic passed: 12 checks" in output.getvalue()


def diagnostic_button_class(count=9):
    return SimpleNamespace(type=xinput.ButtonClass, state=[False] * count)


def diagnostic_master_pointer(
    deviceid=2,
    *,
    enabled=True,
    use=xinput.MasterPointer,
    classes=None,
):
    if classes is None:
        classes = [diagnostic_button_class()]
    return SimpleNamespace(
        deviceid=deviceid,
        enabled=enabled,
        use=use,
        classes=classes,
    )


def test_xinput_topology_accepts_xi2_and_one_master_pointer():
    detail = runtime.check_xinput_topology(
        ":99",
        SimpleNamespace(major_version=2, minor_version=0),
        [
            diagnostic_master_pointer(7),
            SimpleNamespace(
                deviceid=8,
                enabled=True,
                use=xinput.MasterKeyboard,
                classes=[],
            ),
        ],
    )

    assert detail == "XI2 2.0 on ':99'; master pointer id=7, 9 buttons"


@pytest.mark.parametrize(
    ("version", "devices", "message"),
    (
        ((1, 9), [diagnostic_master_pointer()], "XI2 2.0"),
        ((2, 0), [], "exactly one enabled master pointer, got 0"),
        (
            (2, 0),
            [diagnostic_master_pointer(enabled=False)],
            "exactly one enabled master pointer, got 0",
        ),
        (
            (2, 0),
            [diagnostic_master_pointer(use=xinput.SlavePointer)],
            "exactly one enabled master pointer, got 0",
        ),
        (
            (2, 0),
            [diagnostic_master_pointer(2), diagnostic_master_pointer(4)],
            "exactly one enabled master pointer, got 2",
        ),
        (
            (2, 0),
            [diagnostic_master_pointer(classes=[])],
            "exactly one ButtonClass, got 0",
        ),
        (
            (2, 0),
            [
                diagnostic_master_pointer(
                    classes=[
                        diagnostic_button_class(),
                        diagnostic_button_class(),
                    ]
                )
            ],
            "exactly one ButtonClass, got 2",
        ),
        (
            (2, 0),
            [diagnostic_master_pointer(classes=[diagnostic_button_class(8)])],
            "at least 9 buttons, got 8",
        ),
    ),
)
def test_xinput_topology_rejects_invalid_version_or_devices(
    version,
    devices,
    message,
):
    with pytest.raises(RuntimeError, match=message):
        runtime.check_xinput_topology(
            ":99",
            SimpleNamespace(
                major_version=version[0],
                minor_version=version[1],
            ),
            devices,
        )


def test_xinput_host_preserves_probe_and_close_errors(monkeypatch):
    probe_error = OSError("XIQueryDevice failed")
    close_error = OSError("close failed")

    class FailingDisplay:
        def has_extension(self, name):
            assert name == xinput.extname
            return True

        def xinput_query_version(self):
            return SimpleNamespace(major_version=2, minor_version=0)

        def xinput_query_device(self, deviceid):
            assert deviceid == xinput.AllMasterDevices
            raise probe_error

        def close(self):
            raise close_error

    monkeypatch.setattr(xdisplay, "Display", lambda display: FailingDisplay())

    with pytest.raises(OSError) as caught:
        runtime._check_xinput_host(":99")

    assert caught.value is probe_error
    assert any("close failed" in note for note in probe_error.__notes__)


def test_python_check_accepts_exact_version():
    assert runtime.check_python((3, 11, 11)) == "Python 3.11.11"


@pytest.mark.parametrize("version", ((3, 11, 10), (3, 11, 12), (3, 12, 1)))
def test_python_check_rejects_any_other_version(version):
    actual = ".".join(str(value) for value in version)

    with pytest.raises(
        RuntimeError,
        match=rf"requires Python 3\.11\.11, got {actual}",
    ):
        runtime.check_python(version)


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


@pytest.mark.parametrize(
    "session_type",
    (None, "", "tty", "wayland", "mir", "xorg"),
)
def test_session_check_requires_exact_x11_session_even_with_display(
    session_type,
):
    environ = {"DISPLAY": ":0"}
    if session_type is not None:
        environ["XDG_SESSION_TYPE"] = session_type

    with pytest.raises(
        RuntimeError,
        match=r"XDG_SESSION_TYPE=.*requires x11",
    ):
        runtime.check_session(environ)


def test_session_check_accepts_case_normalized_x11():
    session_type = "X11"
    display_name = ":0"

    detail = runtime.check_session(
        {"XDG_SESSION_TYPE": session_type, "DISPLAY": display_name}
    )

    assert detail == (
        f"XDG_SESSION_TYPE={session_type!r}, "
        f"DISPLAY={display_name!r}"
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


def test_ldd_orbbec_library_rejects_missing_dependency_record(tmp_path):
    extension = tmp_path / "pyorbbecsdk.so"

    def missing(command, **options):
        return SimpleNamespace(
            returncode=0,
            stdout="\tlibstdc++.so.6 => /usr/lib/libstdc++.so.6\n",
            stderr="",
        )

    with pytest.raises(RuntimeError, match="did not resolve libOrbbecSDK"):
        runtime._ldd_orbbec_library(extension, run_command=missing)


def test_ldd_orbbec_library_rejects_missing_resolved_target(tmp_path):
    extension = tmp_path / "pyorbbecsdk.so"
    missing_library = tmp_path / "missing" / "libOrbbecSDK.so.2"

    def missing_target(command, **options):
        return SimpleNamespace(
            returncode=0,
            stdout=f"\tlibOrbbecSDK.so.2 => {missing_library}\n",
            stderr="",
        )

    with pytest.raises(FileNotFoundError):
        runtime._ldd_orbbec_library(extension, run_command=missing_target)


def test_ldd_orbbec_library_rejects_ambiguous_resolutions(tmp_path):
    extension = tmp_path / "pyorbbecsdk.so"
    first = tmp_path / "first" / "libOrbbecSDK.so.2"
    second = tmp_path / "second" / "libOrbbecSDK.so.2"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    def ambiguous(command, **options):
        return SimpleNamespace(
            returncode=0,
            stdout=(
                f"\tlibOrbbecSDK.so.2 => {first}\n"
                f"\tlibOrbbecSDK.so.2.8.6 => {second}\n"
            ),
            stderr="",
        )

    with pytest.raises(RuntimeError, match="resolved 2 libOrbbecSDK entries"):
        runtime._ldd_orbbec_library(extension, run_command=ambiguous)


def bundled_orbbec_sdk(tmp_path):
    package_directory = tmp_path / "pyorbbecsdk"
    package_directory.mkdir()
    module_file = package_directory / "__init__.py"
    extension = package_directory / "pyorbbecsdk.cpython-311-x86_64-linux-gnu.so"
    real_library = package_directory / "libOrbbecSDK.so.2.8.6"
    library_entry = package_directory / "libOrbbecSDK.so.2"
    module_file.write_text("")
    extension.write_bytes(b"extension")
    real_library.write_bytes(b"sdk")
    library_entry.symlink_to(real_library.name)
    module = SimpleNamespace(
        __file__=str(module_file),
        get_version=lambda: "2.8.6",
    )
    return module, package_directory, extension, library_entry, real_library


def installed_orbbec_distribution(package_directory):
    package_entry = Path("pyorbbecsdk/__init__.py")
    return SimpleNamespace(
        version="2.1.1",
        files=(package_entry,),
        locate_file=lambda relative_path: (
            package_directory.parent / relative_path
        ),
    )


def test_orbbec_abi_check_accepts_internal_symlink_to_bundled_sdk(tmp_path):
    _, package_directory, _, bundled, real_library = bundled_orbbec_sdk(
        tmp_path
    )

    detail = runtime.check_orbbec_abi(
        binding_version="2.1.1",
        sdk_version="2.8.6",
        resolved_library=bundled,
        expected_library=bundled,
        package_directory=package_directory,
    )

    assert detail == (
        "pyorbbecsdk2=2.1.1, SDK=2.8.6, "
        f"bundled libOrbbecSDK={real_library}; "
        "system SDK discovery=not found (informational only)"
    )


def test_orbbec_abi_check_prints_system_sdk_as_informational_only(tmp_path):
    _, package_directory, _, bundled, real_library = bundled_orbbec_sdk(
        tmp_path
    )
    system = Path("/usr/local/lib/libOrbbecSDK.so.2.9.3")

    detail = runtime.check_orbbec_abi(
        binding_version="2.1.1",
        sdk_version="2.8.6",
        resolved_library=bundled,
        expected_library=bundled,
        package_directory=package_directory,
        system_library=system,
    )

    assert f"bundled libOrbbecSDK={real_library}" in detail
    assert detail.endswith(
        "system SDK discovery="
        "/usr/local/lib/libOrbbecSDK.so.2.9.3 "
        "(informational only)"
    )


def test_orbbec_abi_check_rejects_system_library_resolution(tmp_path):
    _, package_directory, _, bundled, _ = bundled_orbbec_sdk(tmp_path)
    system = tmp_path / "usr" / "local" / "lib" / "libOrbbecSDK.so.2.9.3"
    system.parent.mkdir(parents=True)
    system.write_bytes(b"system sdk")

    with pytest.raises(RuntimeError) as captured:
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.8.6",
            resolved_library=system,
            expected_library=bundled,
            package_directory=package_directory,
        )

    message = str(captured.value)
    assert "outside canonical imported package directory" in message
    assert "SDK version expected" not in message


def test_orbbec_abi_check_rejects_sibling_prefix_escape(tmp_path):
    _, package_directory, _, _, _ = bundled_orbbec_sdk(tmp_path)
    sibling = tmp_path / "pyorbbecsdk-escape"
    sibling.mkdir()
    escaped = sibling / "libOrbbecSDK.so.2.8.6"
    escaped.write_bytes(b"external sdk")

    with pytest.raises(
        RuntimeError,
        match="outside canonical imported package directory",
    ):
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.8.6",
            resolved_library=escaped,
            expected_library=escaped,
            package_directory=package_directory,
        )


def test_orbbec_abi_check_rejects_bundled_symlink_to_external_target(
    tmp_path,
):
    package_directory = tmp_path / "pyorbbecsdk"
    package_directory.mkdir()
    external = tmp_path / "external" / "libOrbbecSDK.so.2.8.6"
    external.parent.mkdir()
    external.write_bytes(b"external sdk")
    bundled = package_directory / "libOrbbecSDK.so.2"
    bundled.symlink_to(external)

    with pytest.raises(
        RuntimeError,
        match="outside canonical imported package directory",
    ):
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.8.6",
            resolved_library=external,
            expected_library=bundled,
            package_directory=package_directory,
        )


def test_orbbec_abi_check_rejects_different_internal_library(tmp_path):
    _, package_directory, _, bundled, _ = bundled_orbbec_sdk(tmp_path)
    other = package_directory / "libOrbbecSDK.so.2.7.0"
    other.write_bytes(b"wrong internal sdk")

    with pytest.raises(RuntimeError) as captured:
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.8.6",
            resolved_library=other,
            expected_library=bundled,
            package_directory=package_directory,
        )

    assert "bundled libOrbbecSDK expected" in str(captured.value)
    assert f"got {other}" in str(captured.value)


def test_orbbec_abi_check_rejects_another_sdk_version(tmp_path):
    _, package_directory, _, bundled, _ = bundled_orbbec_sdk(tmp_path)

    with pytest.raises(
        RuntimeError,
        match=r"SDK version expected 2\.8\.6, got 2\.9\.3",
    ):
        runtime.check_orbbec_abi(
            binding_version="2.1.1",
            sdk_version="2.9.3",
            resolved_library=bundled,
            expected_library=bundled,
            package_directory=package_directory,
        )


def test_orbbec_abi_host_accepts_matching_distribution_and_import_provenance(
    monkeypatch,
    tmp_path,
):
    module, package_directory, extension, bundled, real_library = (
        bundled_orbbec_sdk(tmp_path)
    )
    distribution = installed_orbbec_distribution(package_directory)
    distribution_calls = []
    system = Path("/usr/local/lib/libOrbbecSDK.so.2.9.3")
    monkeypatch.setattr(runtime, "_import_orbbec", lambda: module)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "distribution",
        lambda name: distribution_calls.append(name) or distribution,
    )
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "version",
        lambda name: pytest.fail("must use the same Distribution object"),
    )
    monkeypatch.setattr(runtime, "_orbbec_extension", lambda loaded: extension)
    monkeypatch.setattr(
        runtime,
        "_ldd_orbbec_library",
        lambda loaded_extension: bundled.resolve(),
    )
    monkeypatch.setattr(
        runtime,
        "_informational_system_orbbec_library",
        lambda: system,
        raising=False,
    )

    detail = runtime._check_orbbec_abi_host()

    assert distribution_calls == ["pyorbbecsdk2"]
    assert f"bundled libOrbbecSDK={real_library}" in detail
    assert f"system SDK discovery={system}" in detail


def test_orbbec_abi_host_rejects_shadow_import_with_installed_metadata(
    monkeypatch,
    tmp_path,
):
    installed_root = tmp_path / "installed"
    installed_root.mkdir()
    _, installed_package, _, _, _ = bundled_orbbec_sdk(installed_root)
    distribution = installed_orbbec_distribution(installed_package)

    shadow_root = tmp_path / "shadow"
    shadow_root.mkdir()
    shadow_module, _, shadow_extension, shadow_library, _ = (
        bundled_orbbec_sdk(shadow_root)
    )
    shadow_module.get_version = lambda: pytest.fail(
        "shadow module API must not run before provenance validation"
    )
    monkeypatch.setattr(runtime, "_import_orbbec", lambda: shadow_module)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "distribution",
        lambda name: distribution,
    )
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "version",
        lambda name: "2.1.1",
    )
    monkeypatch.setattr(
        runtime,
        "_orbbec_extension",
        lambda loaded: shadow_extension,
    )
    monkeypatch.setattr(
        runtime,
        "_ldd_orbbec_library",
        lambda loaded_extension: shadow_library.resolve(),
    )
    monkeypatch.setattr(
        runtime,
        "_informational_system_orbbec_library",
        lambda: None,
        raising=False,
    )

    with pytest.raises(
        RuntimeError,
        match="pyorbbecsdk import provenance mismatch",
    ):
        runtime._check_orbbec_abi_host()


def test_orbbec_abi_host_rejects_external_package_entry_symlink(
    monkeypatch,
    tmp_path,
):
    package_directory = tmp_path / "pyorbbecsdk"
    package_directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    module_file = package_directory / "__init__.py"
    external_module = outside / "__init__.py"
    external_module.write_text("")
    module_file.symlink_to(external_module)
    extension = package_directory / "pyorbbecsdk.cpython-311-x86_64-linux-gnu.so"
    extension.write_bytes(b"extension")
    external_library = outside / "libOrbbecSDK.so.2"
    external_library.write_bytes(b"external sdk")
    module = SimpleNamespace(
        __file__=str(module_file),
        get_version=lambda: "2.8.6",
    )
    monkeypatch.setattr(runtime, "_import_orbbec", lambda: module)
    monkeypatch.setattr(
        runtime.importlib.metadata,
        "version",
        lambda distribution: "2.1.1",
    )
    monkeypatch.setattr(runtime, "_orbbec_extension", lambda loaded: extension)
    monkeypatch.setattr(
        runtime,
        "_ldd_orbbec_library",
        lambda loaded_extension: external_library.resolve(),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "package entry resolves outside canonical imported "
            "package directory"
        ),
    ):
        runtime._check_orbbec_abi_host()


def test_orbbec_abi_check_rejects_wrong_binding_distribution_version(
    tmp_path,
):
    _, package_directory, _, bundled, _ = bundled_orbbec_sdk(tmp_path)

    with pytest.raises(
        RuntimeError,
        match=r"binding expected 2\.1\.1, got 2\.2\.0",
    ):
        runtime.check_orbbec_abi(
            binding_version="2.2.0",
            sdk_version="2.8.6",
            resolved_library=bundled,
            expected_library=bundled,
            package_directory=package_directory,
        )
