#!/usr/bin/env python3
"""Read-only Ubuntu installation prerequisite checks for NeuGaze."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import stat
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence, TextIO


EXPECTED_PYTHON = (3, 11, 11)
EXPECTED_UDEV_SOURCE_SHA256 = (
    "71a727fbe198a93213d6d6a62a91040da87489065420ff01d102d6334c89a25b"
)
UDEV_SETUP_DIRECTORY = Path("scripts/env_setup")
UDEV_INSTALLER_NAME = "install_udev_rules.sh"
UDEV_RULE_NAME = "99-obsensor-libusb.rules"
INSTALLED_UDEV_RULE = Path("/etc/udev/rules.d/99-obsensor-libusb.rules")
GEMINI_335_VENDOR_RULE = b"ATTRS{idVendor}==\"2bc5\""
GEMINI_335_PRODUCT_RULE = b"ATTRS{idProduct}==\"0800\""


@dataclass(frozen=True)
class CheckFailure:
    name: str
    error: Exception
    formatted_traceback: str


def execute_checks(
    checks: Iterable[tuple[str, Callable[[], str]]],
    output: TextIO,
) -> list[CheckFailure]:
    failures = []
    check_count = 0
    for name, check in checks:
        check_count += 1
        try:
            detail = check()
        except Exception as error:
            formatted = traceback.format_exc()
            failures.append(CheckFailure(name, error, formatted))
            print(
                f"[FAIL] {name}: {type(error).__name__}: {error}",
                file=output,
            )
        else:
            print(f"[PASS] {name}: {detail}", file=output)

    if not failures:
        print(
            f"Installation check passed: {check_count} checks",
            file=output,
        )
        return failures

    print(
        f"Installation check failed with {len(failures)} failure(s):",
        file=output,
    )
    for failure in failures:
        print(
            f"- {failure.name}: {type(failure.error).__name__}: "
            f"{failure.error}",
            file=output,
        )
        print(failure.formatted_traceback.rstrip(), file=output)
    return failures


def check_platform(
    platform_name: str,
    os_release: Mapping[str, str],
    machine: str,
) -> str:
    if platform_name != "linux":
        raise RuntimeError(
            f"NeuGaze installation checker requires Linux, got "
            f"{platform_name!r}"
        )
    distribution = os_release.get("ID")
    version = os_release.get("VERSION_ID")
    if distribution != "ubuntu" or version != "24.04":
        raise RuntimeError(
            "NeuGaze requires Ubuntu 24.04; "
            f"got ID={distribution!r}, VERSION_ID={version!r}"
        )
    if machine != "x86_64":
        raise RuntimeError(
            f"NeuGaze Ubuntu installation requires x86_64, got {machine!r}"
        )
    return f"Ubuntu 24.04 x86_64, kernel {platform.release()}"


def check_python(version_info: Sequence[int]) -> str:
    version = tuple(int(value) for value in version_info[:3])
    actual = ".".join(str(value) for value in version)
    if version != EXPECTED_PYTHON:
        raise RuntimeError(
            "NeuGaze requires Python 3.11.11, "
            f"got {actual}"
        )
    return f"Python {actual}"


def check_conda_environment(
    prefix: str | Path,
    environ: Mapping[str, str],
) -> str:
    prefix_path = Path(prefix)
    try:
        canonical_prefix = prefix_path.resolve(strict=True)
    except OSError as error:
        raise RuntimeError(
            f"sys.prefix does not resolve to an existing environment: "
            f"{prefix_path}"
        ) from error
    history = canonical_prefix / "conda-meta/history"
    if not history.is_file():
        raise RuntimeError(
            f"Conda environment marker is missing: {history}"
        )
    conda_prefix_value = environ.get("CONDA_PREFIX")
    if not conda_prefix_value:
        raise RuntimeError("CONDA_PREFIX is not set")
    try:
        canonical_conda_prefix = Path(conda_prefix_value).resolve(strict=True)
    except OSError as error:
        raise RuntimeError(
            f"CONDA_PREFIX does not resolve: {conda_prefix_value!r}"
        ) from error
    if canonical_conda_prefix != canonical_prefix:
        raise RuntimeError(
            f"CONDA_PREFIX {canonical_conda_prefix} does not match "
            f"sys.prefix {canonical_prefix}"
        )
    if canonical_prefix.name != "neugaze":
        raise RuntimeError(
            f"Conda environment basename must be neugaze, got "
            f"{canonical_prefix.name!r}"
        )
    return f"Conda environment neugaze at {canonical_prefix}"


def check_dpkg_package(
    package: str,
    run_command: Callable[..., object] | None = None,
) -> str:
    if run_command is None:
        run_command = subprocess.run
    command = (
        "dpkg-query",
        "--show",
        "--showformat=${Status}",
        package,
    )
    result = run_command(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command {command!r} exited {result.returncode}; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    status_value = result.stdout.strip()
    if status_value != "install ok installed":
        raise RuntimeError(
            f"Debian package {package!r} is not installed; "
            f"command {command!r} exited {result.returncode}; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    return f"Debian package {package} is installed"


def check_command(
    command: str,
    which: Callable[[str], str | None] | None = None,
) -> str:
    if which is None:
        which = shutil.which
    resolved = which(command)
    if resolved is None:
        raise RuntimeError(f"required command {command!r} was not found")
    return resolved


def _source_rule_path(sdk_root: Path) -> Path:
    return sdk_root / UDEV_SETUP_DIRECTORY / UDEV_RULE_NAME


def check_sdk_layout(sdk_root: str | Path) -> str:
    root = Path(sdk_root)
    if not root.is_absolute():
        raise RuntimeError(
            f"--orbbec-sdk-root must be absolute, got {root}"
        )
    if not root.is_dir():
        raise RuntimeError(f"Orbbec SDK root does not exist: {root}")
    setup = root / UDEV_SETUP_DIRECTORY
    installer = setup / UDEV_INSTALLER_NAME
    source = setup / UDEV_RULE_NAME
    missing = [path for path in (installer, source) if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Orbbec SDK udev file(s) missing: "
            + ", ".join(str(path) for path in missing)
        )
    return f"{root}: {installer.name} and {source.name} exist"


def check_udev_source(
    sdk_root: str | Path,
    expected_sha256: str = EXPECTED_UDEV_SOURCE_SHA256,
) -> str:
    source = _source_rule_path(Path(sdk_root))
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise RuntimeError(
            f"Orbbec udev source SHA-256 expected {expected_sha256}, "
            f"got {digest} for {source}"
        )
    if not any(
        GEMINI_335_VENDOR_RULE in line
        and GEMINI_335_PRODUCT_RULE in line
        for line in payload.splitlines()
    ):
        raise RuntimeError(
            f"Orbbec udev source {source} lacks Gemini 335 rule 2bc5:0800"
        )
    return f"{source}: SHA-256 {digest}; Gemini 335 rule 2bc5:0800"


def check_installed_udev_rule(
    sdk_root: str | Path,
    installed_path: Path = INSTALLED_UDEV_RULE,
    stat_file: Callable[[Path], os.stat_result] | None = None,
) -> str:
    if stat_file is None:
        stat_file = lambda path: path.stat()
    source = _source_rule_path(Path(sdk_root))
    source_payload = source.read_bytes()
    installed_payload = installed_path.read_bytes()
    installed_stat = stat_file(installed_path)
    if installed_stat.st_uid != 0:
        raise RuntimeError(
            f"installed udev rule {installed_path} must be owned by uid 0, "
            f"got {installed_stat.st_uid}"
        )
    mode = stat.S_IMODE(installed_stat.st_mode)
    if mode & 0o022:
        raise RuntimeError(
            f"installed udev rule {installed_path} is group/world writable: "
            f"mode {mode:04o}"
        )
    if installed_payload != source_payload:
        raise RuntimeError(
            f"installed udev rule {installed_path} does not exactly match "
            f"source {source}"
        )
    return (
        f"{installed_path}: root-owned, mode {mode:04o}, "
        "bytes exactly match SDK source"
    )


def build_checks(
    sdk_root: Path,
    require_overlay: bool,
    require_test_tools: bool,
) -> tuple[tuple[str, Callable[[], str]], ...]:
    checks = [
        (
            "Platform",
            lambda: check_platform(
                sys.platform,
                platform.freedesktop_os_release(),
                platform.machine(),
            ),
        ),
        ("Python", lambda: check_python(sys.version_info)),
        (
            "Conda environment",
            lambda: check_conda_environment(sys.prefix, os.environ),
        ),
        (
            "Package libxcb-cursor0",
            lambda: check_dpkg_package("libxcb-cursor0"),
        ),
        ("Command udevadm", lambda: check_command("udevadm")),
        ("Orbbec SDK layout", lambda: check_sdk_layout(sdk_root)),
        ("Orbbec udev source", lambda: check_udev_source(sdk_root)),
        (
            "Installed Orbbec udev rule",
            lambda: check_installed_udev_rule(sdk_root),
        ),
    ]
    if require_overlay:
        checks.extend(
            (
                (
                    "Package xcompmgr",
                    lambda: check_dpkg_package("xcompmgr"),
                ),
                ("Command xcompmgr", lambda: check_command("xcompmgr")),
            )
        )
    if require_test_tools:
        checks.extend(
            (
                ("Package xvfb", lambda: check_dpkg_package("xvfb")),
                ("Command Xvfb", lambda: check_command("Xvfb")),
                ("Command xvfb-run", lambda: check_command("xvfb-run")),
                ("Command xauth", lambda: check_command("xauth")),
            )
        )
    return tuple(checks)


def _absolute_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError(
            f"--orbbec-sdk-root must be absolute, got {value!r}"
        )
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check NeuGaze Ubuntu installation prerequisites without "
            "changing the host"
        )
    )
    parser.add_argument(
        "--orbbec-sdk-root",
        required=True,
        type=_absolute_path,
        help="absolute Orbbec SDK source root used only for udev verification",
    )
    parser.add_argument(
        "--require-overlay",
        action="store_true",
        help="require xcompmgr and libxcb-cursor0 overlay prerequisites",
    )
    parser.add_argument(
        "--require-test-tools",
        action="store_true",
        help="require Xvfb, xvfb-run, and xauth test tools",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    failures = execute_checks(
        build_checks(
            args.orbbec_sdk_root,
            args.require_overlay,
            args.require_test_tools,
        ),
        sys.stdout,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
