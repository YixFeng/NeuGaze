import ast
import hashlib
import io
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_ubuntu_install as install


EXPECTED_SHA256 = (
    "71a727fbe198a93213d6d6a62a91040da87489065420ff01d102d6334c89a25b"
)
RULE_BYTES = (
    b"SUBSYSTEMS==\"usb\", ATTRS{idVendor}==\"2bc5\", "
    b"ATTRS{idProduct}==\"0800\", MODE:=\"0666\"\n"
)


def make_sdk_root(tmp_path, rule_bytes=RULE_BYTES):
    root = tmp_path / "OrbbecSDK_v2"
    setup = root / "scripts/env_setup"
    setup.mkdir(parents=True)
    (setup / "install_udev_rules.sh").write_text("#!/bin/sh\n")
    source = setup / "99-obsensor-libusb.rules"
    source.write_bytes(rule_bytes)
    return root, source



def test_module_uses_only_python_standard_library():
    source = Path(install.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    assert imported_roots <= stdlib


def test_execute_checks_reports_success_one_line_per_check():
    output = io.StringIO()

    failures = install.execute_checks(
        (
            ("Python", lambda: "Python 3.11.11"),
            ("udevadm", lambda: "/usr/bin/udevadm"),
        ),
        output,
    )

    assert failures == []
    assert output.getvalue().splitlines() == [
        "[PASS] Python: Python 3.11.11",
        "[PASS] udevadm: /usr/bin/udevadm",
        "Installation check passed: 2 checks",
    ]


def test_execute_checks_aggregates_all_failures_with_tracebacks():
    output = io.StringIO()
    first = RuntimeError("package missing")
    second = OSError("rule unreadable")

    failures = install.execute_checks(
        (
            ("Package", lambda: (_ for _ in ()).throw(first)),
            ("Rule", lambda: (_ for _ in ()).throw(second)),
        ),
        output,
    )

    assert [failure.error for failure in failures] == [first, second]
    report = output.getvalue()
    assert "[FAIL] Package: RuntimeError: package missing" in report
    assert "[FAIL] Rule: OSError: rule unreadable" in report
    assert "Installation check failed with 2 failure(s):" in report
    assert report.count("Traceback (most recent call last):") == 2


def test_platform_and_python_require_exact_supported_values():
    assert install.check_platform(
        "linux", {"ID": "ubuntu", "VERSION_ID": "24.04"}, "x86_64"
    ).startswith("Ubuntu 24.04 x86_64")
    assert install.check_python((3, 11, 11)) == "Python 3.11.11"


@pytest.mark.parametrize(
    ("platform_name", "os_release", "machine", "message"),
    (
        ("win32", {"ID": "ubuntu", "VERSION_ID": "24.04"}, "x86_64", "requires Linux"),
        ("linux", {"ID": "debian", "VERSION_ID": "24.04"}, "x86_64", "requires Ubuntu 24.04"),
        ("linux", {"ID": "ubuntu", "VERSION_ID": "22.04"}, "x86_64", "requires Ubuntu 24.04"),
        ("linux", {"ID": "ubuntu", "VERSION_ID": "24.04"}, "aarch64", "requires x86_64"),
    ),
)
def test_platform_rejects_wrong_os_version_or_architecture(
    platform_name, os_release, machine, message
):
    with pytest.raises(RuntimeError, match=message):
        install.check_platform(platform_name, os_release, machine)


@pytest.mark.parametrize("version", ((3, 11, 10), (3, 11, 12), (3, 12, 0)))
def test_python_rejects_every_non_exact_version(version):
    with pytest.raises(RuntimeError, match="requires Python 3.11.11"):
        install.check_python(version)


def test_conda_environment_requires_exact_canonical_neugaze_prefix(tmp_path):
    prefix = tmp_path / "envs/neugaze"
    (prefix / "conda-meta").mkdir(parents=True)
    (prefix / "conda-meta/history").write_text("created")
    alias = tmp_path / "neugaze-link"
    alias.symlink_to(prefix, target_is_directory=True)

    detail = install.check_conda_environment(prefix, {"CONDA_PREFIX": str(alias)})

    assert str(prefix.resolve()) in detail
    assert "neugaze" in detail


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("missing_history", "conda-meta/history"),
        ("missing_env", "CONDA_PREFIX"),
        ("mismatch", "does not match sys.prefix"),
        ("wrong_name", "basename must be neugaze"),
    ),
)
def test_conda_environment_rejects_invalid_contract(tmp_path, case, message):
    prefix = tmp_path / "envs/neugaze"
    (prefix / "conda-meta").mkdir(parents=True)
    history = prefix / "conda-meta/history"
    if case != "missing_history":
        history.write_text("created")
    environ = {"CONDA_PREFIX": str(prefix)}
    if case == "missing_env":
        environ = {}
    elif case == "mismatch":
        other = tmp_path / "envs/other"
        other.mkdir()
        environ = {"CONDA_PREFIX": str(other)}
    elif case == "wrong_name":
        wrong = tmp_path / "envs/not-neugaze"
        (wrong / "conda-meta").mkdir(parents=True)
        (wrong / "conda-meta/history").write_text("created")
        prefix = wrong
        environ = {"CONDA_PREFIX": str(wrong)}

    with pytest.raises(RuntimeError, match=message):
        install.check_conda_environment(prefix, environ)


def test_dpkg_check_uses_read_only_query_and_reports_installed():
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 0, "install ok installed", "")

    detail = install.check_dpkg_package("xvfb", run_command=run)

    assert "xvfb" in detail
    assert calls == [
        (
            ("dpkg-query", "--show", "--showformat=${Status}", "xvfb"),
            {"check": False, "capture_output": True, "text": True},
        )
    ]


def test_dpkg_check_preserves_exit_code_stdout_and_stderr():
    def run(command, **options):
        return subprocess.CompletedProcess(command, 7, "query stdout", "query stderr")

    with pytest.raises(RuntimeError) as caught:
        install.check_dpkg_package("xvfb", run_command=run)

    message = str(caught.value)
    assert "exited 7" in message
    assert "query stdout" in message
    assert "query stderr" in message


def test_dpkg_check_rejects_noninstalled_status_even_on_zero_exit():
    def run(command, **options):
        return subprocess.CompletedProcess(
            command, 0, "deinstall ok config-files", "query stderr"
        )

    with pytest.raises(RuntimeError) as caught:
        install.check_dpkg_package("xvfb", run_command=run)

    message = str(caught.value)
    assert "not installed" in message
    assert "exited 0" in message
    assert "deinstall ok config-files" in message
    assert "query stderr" in message


def test_command_check_requires_exact_executable():
    assert install.check_command("udevadm", which=lambda name: "/usr/bin/udevadm") == "/usr/bin/udevadm"
    with pytest.raises(RuntimeError, match="udevadm.*not found"):
        install.check_command("udevadm", which=lambda name: None)


def test_sdk_layout_requires_absolute_root_installer_and_source(tmp_path):
    root, source = make_sdk_root(tmp_path)

    detail = install.check_sdk_layout(root)

    assert str(root) in detail
    assert source.name in detail
    with pytest.raises(RuntimeError, match="absolute"):
        install.check_sdk_layout(Path("relative-sdk"))
    (root / "scripts/env_setup/install_udev_rules.sh").unlink()
    with pytest.raises(RuntimeError, match="install_udev_rules.sh"):
        install.check_sdk_layout(root)


def test_udev_source_requires_exact_checksum_and_gemini_product_rule(tmp_path):
    root, source = make_sdk_root(tmp_path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    detail = install.check_udev_source(root, expected_sha256=digest)

    assert digest in detail
    assert "2bc5:0800" in detail
    assert install.EXPECTED_UDEV_SOURCE_SHA256 == EXPECTED_SHA256


def test_udev_source_rejects_checksum_before_accepting_content(tmp_path):
    root, _ = make_sdk_root(tmp_path)

    with pytest.raises(RuntimeError, match="SHA-256"):
        install.check_udev_source(root)


def test_udev_source_rejects_missing_gemini_product_rule(tmp_path):
    root, source = make_sdk_root(tmp_path, b"unrelated rule\n")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="2bc5:0800"):
        install.check_udev_source(root, expected_sha256=digest)


def test_installed_udev_rule_requires_root_safe_mode_and_exact_bytes(tmp_path):
    root, source = make_sdk_root(tmp_path)
    installed = tmp_path / "etc/udev/rules.d/99-obsensor-libusb.rules"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(source.read_bytes())
    safe = SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644)

    detail = install.check_installed_udev_rule(
        root,
        installed_path=installed,
        stat_file=lambda path: safe,
    )

    assert "root-owned" in detail
    assert "mode 0644" in detail


@pytest.mark.parametrize(
    ("file_stat", "installed_bytes", "message"),
    (
        (SimpleNamespace(st_uid=1000, st_mode=stat.S_IFREG | 0o644), RULE_BYTES, "owned by uid 0"),
        (SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o664), RULE_BYTES, "group/world writable"),
        (SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o646), RULE_BYTES, "group/world writable"),
        (SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o644), b"different", "does not exactly match"),
    ),
)
def test_installed_udev_rule_rejects_owner_mode_or_content(
    tmp_path, file_stat, installed_bytes, message
):
    root, _ = make_sdk_root(tmp_path)
    installed = tmp_path / "installed.rules"
    installed.write_bytes(installed_bytes)

    with pytest.raises(RuntimeError, match=message):
        install.check_installed_udev_rule(
            root,
            installed_path=installed,
            stat_file=lambda path: file_stat,
        )


def test_build_checks_adds_overlay_and_test_tools_only_when_requested(monkeypatch, tmp_path):
    root, _ = make_sdk_root(tmp_path)
    monkeypatch.setattr(install, "check_platform", lambda *args: "platform")
    monkeypatch.setattr(install, "check_python", lambda *args: "python")
    monkeypatch.setattr(install, "check_conda_environment", lambda *args: "conda")
    monkeypatch.setattr(install, "check_dpkg_package", lambda package: f"dpkg {package}")
    monkeypatch.setattr(install, "check_command", lambda command: f"which {command}")
    monkeypatch.setattr(install, "check_sdk_layout", lambda path: "layout")
    monkeypatch.setattr(install, "check_udev_source", lambda path: "source")
    monkeypatch.setattr(install, "check_installed_udev_rule", lambda path: "installed")

    base_names = [name for name, _ in install.build_checks(root, False, False)]
    full_names = [name for name, _ in install.build_checks(root, True, True)]

    assert base_names == [
        "Platform", "Python", "Conda environment", "Package libxcb-cursor0",
        "Command udevadm", "Orbbec SDK layout", "Orbbec udev source",
        "Installed Orbbec udev rule",
    ]
    assert full_names == base_names + [
        "Package xcompmgr", "Command xcompmgr", "Package xvfb",
        "Command Xvfb", "Command xvfb-run", "Command xauth",
    ]


def test_full_check_execution_invokes_only_read_only_system_commands(monkeypatch, tmp_path):
    root, _ = make_sdk_root(tmp_path)
    commands = []
    which_calls = []

    def run(command, **options):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "install ok installed", "")

    monkeypatch.setattr(install.subprocess, "run", run)
    monkeypatch.setattr(
        install.shutil,
        "which",
        lambda name: which_calls.append(name) or f"/usr/bin/{name}",
    )
    monkeypatch.setattr(install, "check_platform", lambda *args: "platform")
    monkeypatch.setattr(install, "check_python", lambda *args: "python")
    monkeypatch.setattr(install, "check_conda_environment", lambda *args: "conda")
    monkeypatch.setattr(install, "check_sdk_layout", lambda path: "layout")
    monkeypatch.setattr(install, "check_udev_source", lambda path: "source")
    monkeypatch.setattr(install, "check_installed_udev_rule", lambda path: "installed")

    failures = install.execute_checks(install.build_checks(root, True, True), io.StringIO())

    assert failures == []
    assert [command[-1] for command in commands] == ["libxcb-cursor0", "xcompmgr", "xvfb"]
    assert all(command[0] == "dpkg-query" for command in commands)
    assert which_calls == ["udevadm", "xcompmgr", "Xvfb", "xvfb-run", "xauth"]
    forbidden = {"sudo", "apt", "apt-get", "cp", "chmod", "udevadm"}
    assert not any(part in forbidden for command in commands for part in command)


def test_cli_requires_absolute_sdk_root_and_exposes_flags():
    with pytest.raises(SystemExit):
        install.parse_args(["--orbbec-sdk-root", "relative"])
    args = install.parse_args(
        [
            "--orbbec-sdk-root", "/opt/OrbbecSDK_v2",
            "--require-overlay", "--require-test-tools",
        ]
    )
    assert args.orbbec_sdk_root == Path("/opt/OrbbecSDK_v2")
    assert args.require_overlay is True
    assert args.require_test_tools is True
