#!/usr/bin/env python3
"""Read-only Ubuntu/Xorg runtime diagnostics for NeuGaze."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence, TextIO

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PYTHON = (3, 11)
EXPECTED_ORBBEC_BINDING = "2.1.1"
EXPECTED_ORBBEC_SDK = "2.9.3"
EXPECTED_ORBBEC_LIBRARY = Path(
    "/usr/local/lib/libOrbbecSDK.so.2.9.3"
)


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
        print(f"Diagnostic passed: {check_count} checks", file=output)
        return failures

    print(
        f"Diagnostic failed with {len(failures)} failure(s):",
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


def check_python(version_info: Sequence[int]) -> str:
    version = tuple(int(value) for value in version_info[:3])
    actual = ".".join(str(value) for value in version)
    if version[:2] != EXPECTED_PYTHON:
        raise RuntimeError(
            f"NeuGaze requires Python 3.11, got {actual}"
        )
    return f"Python {actual}"


def check_platform(
    platform_name: str,
    os_release: Mapping[str, str],
    machine: str,
) -> str:
    if platform_name != "linux":
        raise RuntimeError(
            f"Ubuntu runtime diagnostics require Linux, got "
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
            f"NeuGaze Ubuntu runtime requires x86_64, got {machine!r}"
        )
    return f"Ubuntu 24.04 x86_64, kernel {platform.release()}"


def check_session(environ: Mapping[str, str]) -> str:
    session_type = environ.get("XDG_SESSION_TYPE")
    if session_type is not None and session_type.lower() == "wayland":
        raise RuntimeError(
            f"XDG_SESSION_TYPE={session_type!r} is unsupported; "
            "NeuGaze requires Xorg"
        )
    display_name = environ.get("DISPLAY")
    if display_name is None or not display_name.strip():
        raise RuntimeError(
            f"DISPLAY must name an X11 server, got {display_name!r}"
        )
    return (
        f"XDG_SESSION_TYPE={session_type!r}, "
        f"DISPLAY={display_name!r}"
    )


def check_x11_extension(
    display_name: str,
    extensions: Iterable[str],
    required_extension: str,
) -> str:
    extension_names = set(extensions)
    if required_extension not in extension_names:
        raise RuntimeError(
            f"X11 display {display_name!r} is missing required "
            f"extension {required_extension}"
        )
    return f"{required_extension} is available on {display_name!r}"


def check_compositor(
    config: Mapping[str, object],
    require_overlay: bool,
    owner_exists: bool,
) -> str:
    real_action = config.get("real_action_config")
    if not isinstance(real_action, Mapping):
        raise TypeError("real_action_config must be a mapping")
    show_gaze = real_action.get("show_gaze")
    if not isinstance(show_gaze, bool):
        raise TypeError("real_action_config.show_gaze must be a boolean")
    required = require_overlay or show_gaze
    if required and not owner_exists:
        raise RuntimeError(
            "X11 compositor selection _NET_WM_CM_S0 has no owner"
        )
    if required:
        return "X11 compositor owns _NET_WM_CM_S0"
    return "overlay is disabled; compositor is optional"


def _configured_asset_paths(
    config: Mapping[str, object],
    repository_root: Path,
) -> list[Path]:
    integrated = config.get("integrated_config")
    if not isinstance(integrated, Mapping):
        raise TypeError("integrated_config must be a mapping")

    weights = integrated.get("weights")
    if not isinstance(weights, str) or not weights:
        raise TypeError("integrated_config.weights must be a path string")

    paths = [
        repository_root
        / "models/face_landmarker_v2_with_blendshapes.task",
        repository_root / weights,
    ]
    if paths[-1].suffix == ".param":
        paths.append(paths[-1].with_suffix(".bin"))

    regression_model = integrated.get("regression_model_path")
    if regression_model is not None:
        if not isinstance(regression_model, str) or not regression_model:
            raise TypeError(
                "integrated_config.regression_model_path must be null "
                "or a path string"
            )
        paths.append(repository_root / regression_model)
    return paths


def check_model_assets(
    config: Mapping[str, object],
    repository_root: Path,
) -> str:
    paths = _configured_asset_paths(config, repository_root)
    missing = [
        path
        for path in paths
        if not path.is_file()
    ]
    if missing:
        relative = []
        for path in missing:
            try:
                relative.append(str(path.relative_to(repository_root)))
            except ValueError:
                relative.append(str(path))
        raise RuntimeError(
            "missing required model asset(s): " + ", ".join(relative)
        )
    return f"{len(paths)} required model assets exist"


def _camera_config(
    config: Mapping[str, object],
) -> tuple[str, int, int, int, int]:
    integrated = config.get("integrated_config")
    if not isinstance(integrated, Mapping):
        raise TypeError("integrated_config must be a mapping")
    backends = integrated.get("camera_backend")
    if not isinstance(backends, Mapping):
        raise TypeError(
            "integrated_config.camera_backend must be a platform mapping"
        )
    backend = backends.get("linux")
    if backend not in {"orbbec", "opencv"}:
        raise RuntimeError(
            "integrated_config.camera_backend.linux must be "
            f"orbbec or opencv, got {backend!r}"
        )
    device_id = integrated.get("cam_id")
    if (
        not isinstance(device_id, int)
        or isinstance(device_id, bool)
        or device_id < 0
    ):
        raise RuntimeError(
            "integrated_config.cam_id must be a non-negative integer"
        )

    stream_values = []
    for key in ("camera_width", "camera_height", "camera_fps"):
        value = integrated.get(key)
        if (
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
        ):
            raise RuntimeError(
                f"integrated_config.{key} must be a positive integer"
            )
        stream_values.append(value)
    width, height, fps = stream_values
    return backend, device_id, width, height, fps


def query_orbbec_devices(
    run_command: Callable[..., object] = subprocess.run,
    temporary_directory_factory: Callable[..., object] = (
        tempfile.TemporaryDirectory
    ),
) -> list[dict[str, object]]:
    source = (
        "import json\n"
        "import pyorbbecsdk\n"
        "context = pyorbbecsdk.Context()\n"
        "device_list = context.query_devices()\n"
        "device_count = device_list.get_count()\n"
        "devices = []\n"
        "for index in range(device_count):\n"
        "    info = device_list.get_device_by_index(index).get_device_info()\n"
        "    devices.append({\"index\": index, \"name\": info.get_name(), "
        "\"serial\": info.get_serial_number()})\n"
        "payload = {\"device_count\": device_count, \"devices\": devices}\n"
        "print(\"NEUGAZE_ORBBEC_DEVICES=\" + json.dumps(payload, sort_keys=True))\n"
    )
    command = (sys.executable, "-c", source)
    temporary_directory = temporary_directory_factory(
        prefix="neugaze-orbbec-probe-"
    )
    primary_error = None
    try:
        result = run_command(
            command,
            cwd=temporary_directory.name,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"command {command[:2]!r} exited {result.returncode}; "
                f"stdout={result.stdout!r}; stderr={result.stderr!r}"
            )

        prefix = "NEUGAZE_ORBBEC_DEVICES="
        payload_lines = [
            line[len(prefix):]
            for line in result.stdout.splitlines()
            if line.startswith(prefix)
        ]
        if len(payload_lines) != 1:
            raise RuntimeError(
                f"command {command[:2]!r} returned "
                f"{len(payload_lines)} structured Orbbec results; "
                f"stdout={result.stdout!r}; stderr={result.stderr!r}"
            )
        try:
            payload = json.loads(payload_lines[0])
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"command {command[:2]!r} returned malformed Orbbec data; "
                f"stdout={result.stdout!r}; stderr={result.stderr!r}"
            ) from error

        if not isinstance(payload, dict):
            raise RuntimeError(
                f"malformed Orbbec probe payload: {payload!r}"
            )
        device_count = payload.get("device_count")
        devices = payload.get("devices")
        if (
            not isinstance(device_count, int)
            or isinstance(device_count, bool)
            or not isinstance(devices, list)
            or device_count != len(devices)
        ):
            raise RuntimeError(
                f"malformed Orbbec probe payload: {payload!r}"
            )
        for expected_index, device in enumerate(devices):
            if (
                not isinstance(device, dict)
                or device.get("index") != expected_index
                or not isinstance(device.get("name"), str)
                or not isinstance(device.get("serial"), str)
            ):
                raise RuntimeError(
                    f"malformed Orbbec device entry: {device!r}"
                )
        return devices
    except Exception as error:
        primary_error = error
        raise
    finally:
        try:
            temporary_directory.cleanup()
        except Exception as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                "cleaning Orbbec probe temporary directory also failed: "
                f"{cleanup_error!r}"
            )


def check_camera_selection(
    config: Mapping[str, object],
    platform_name: str,
    device_root: Path = Path("/dev"),
    device_stat: Callable[[Path], object] = os.stat,
    device_access: Callable[[Path, int], bool] = os.access,
    orbbec_devices: Sequence[Mapping[str, object]] | None = None,
) -> str:
    if platform_name != "linux":
        raise RuntimeError(
            f"Ubuntu camera check requires Linux, got {platform_name!r}"
        )
    backend, device_id, width, height, fps = _camera_config(config)
    if backend == "opencv":
        device_path = device_root / f"video{device_id}"
        display_path = f"/dev/video{device_id}"
        try:
            device_info = device_stat(device_path)
        except FileNotFoundError as error:
            raise RuntimeError(
                f"selected OpenCV/V4L2 camera {display_path} "
                "does not exist"
            ) from error
        if not stat.S_ISCHR(device_info.st_mode):
            raise RuntimeError(
                f"selected OpenCV/V4L2 camera {display_path} "
                "is not a character device"
            )
        if not device_access(device_path, os.R_OK | os.W_OK):
            raise RuntimeError(
                f"selected OpenCV/V4L2 camera {display_path} "
                "is not accessible for read/write"
            )
        import cv2

        return (
            f"OpenCV {cv2.__version__}, selected V4L2 device "
            f"{display_path} is an accessible character device; "
            f"configured {width}x{height} at {fps} FPS"
        )

    if (width, height, fps) != (1280, 720, 30):
        raise RuntimeError(
            "Gemini 335 requires 1280x720 at 30 FPS; "
            f"configured {width}x{height} at {fps} FPS"
        )
    devices = (
        query_orbbec_devices()
        if orbbec_devices is None
        else list(orbbec_devices)
    )
    device_count = len(devices)
    if device_id >= device_count:
        raise RuntimeError(
            f"selected Orbbec camera index {device_id} is unavailable; "
            f"detected {device_count} device(s)"
        )
    info = devices[device_id]
    name = info["name"]
    serial = info["serial"]
    if name not in {"Gemini 335", "Orbbec Gemini 335"}:
        raise RuntimeError(
            f"selected Orbbec camera index {device_id} must be "
            f"Gemini 335, got {name!r}"
        )
    return (
        f"Orbbec index {device_id}: name={name!r}, serial={serial!r}; "
        f"configured {width}x{height} at {fps} FPS; "
        f"detected {device_count} device(s)"
    )


def check_orbbec_abi(
    binding_version: str,
    sdk_version: str,
    resolved_library: Path,
    expected_library: Path = EXPECTED_ORBBEC_LIBRARY,
) -> str:
    mismatches = []
    if binding_version != EXPECTED_ORBBEC_BINDING:
        mismatches.append(
            f"binding expected {EXPECTED_ORBBEC_BINDING}, "
            f"got {binding_version}"
        )
    if sdk_version != EXPECTED_ORBBEC_SDK:
        mismatches.append(
            f"SDK version expected {EXPECTED_ORBBEC_SDK}, "
            f"got {sdk_version}"
        )
    if resolved_library != expected_library:
        mismatches.append(
            f"libOrbbecSDK expected {expected_library}, "
            f"got {resolved_library}"
        )
    detail = (
        f"pyorbbecsdk2={binding_version}, SDK={sdk_version}, "
        f"libOrbbecSDK={resolved_library}"
    )
    if mismatches:
        raise RuntimeError(detail + "; " + "; ".join(mismatches))
    return detail


def _load_config(path: Path) -> Mapping[str, object]:
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, Mapping):
        raise TypeError(f"configuration {path} must contain a mapping")
    return config


def _query_x11_extensions(display_name: str) -> set[str]:
    from Xlib import display as xdisplay

    display = xdisplay.Display(display_name)
    primary_error = None
    try:
        return set(display.list_extensions())
    except Exception as error:
        primary_error = error
        raise
    finally:
        try:
            display.close()
        except Exception as close_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"closing X11 display also failed: {close_error!r}"
            )


def _check_x11_display(display_name: str) -> str:
    extensions = _query_x11_extensions(display_name)
    return (
        f"connected to {display_name!r}; "
        f"{len(extensions)} extensions advertised"
    )


def _compositor_owner_exists(display_name: str) -> bool:
    from Xlib import display as xdisplay

    display = xdisplay.Display(display_name)
    primary_error = None
    try:
        atom = display.intern_atom(
            "_NET_WM_CM_S0",
            only_if_exists=True,
        )
        if not atom:
            return False
        return display.get_selection_owner(atom) != 0
    except Exception as error:
        primary_error = error
        raise
    finally:
        try:
            display.close()
        except Exception as close_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"closing X11 display also failed: {close_error!r}"
            )


def _import_orbbec():
    import pyorbbecsdk

    return pyorbbecsdk


def _orbbec_extension(module) -> Path:
    package_dir = Path(module.__file__).resolve().parent
    extensions = sorted(package_dir.glob("pyorbbecsdk*.so"))
    if len(extensions) != 1:
        raise RuntimeError(
            f"expected one pyorbbecsdk extension in {package_dir}, "
            f"found {len(extensions)}: "
            + ", ".join(str(path) for path in extensions)
        )
    return extensions[0]


def _ldd_orbbec_library(
    extension: Path,
    run_command: Callable[..., object] = subprocess.run,
) -> Path:
    command = ("ldd", str(extension))
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
    if re.search(
        r"^\s*libOrbbecSDK\.so(?:\.\d+)*\s+=>\s+not found\s*$",
        result.stdout,
        flags=re.MULTILINE,
    ):
        raise RuntimeError(
            f"command {command!r}: libOrbbecSDK was not found; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    match = re.search(
        r"^\s*libOrbbecSDK\.so(?:\.\d+)*\s+=>\s+(\S+)",
        result.stdout,
        flags=re.MULTILINE,
    )
    if match is None:
        raise RuntimeError(
            f"command {command!r} did not resolve libOrbbecSDK; "
            f"stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
    return Path(match.group(1)).resolve(strict=True)


def _check_orbbec_abi_host() -> str:
    module = _import_orbbec()
    binding_version = importlib.metadata.version("pyorbbecsdk2")
    sdk_version = module.get_version()
    extension = _orbbec_extension(module)
    resolved_library = _ldd_orbbec_library(extension)
    expected_library = EXPECTED_ORBBEC_LIBRARY.resolve(strict=True)
    return check_orbbec_abi(
        binding_version,
        sdk_version,
        resolved_library,
        expected_library,
    )


def _check_config(path: Path) -> str:
    config = _load_config(path)
    backend, device_id, width, height, fps = _camera_config(config)
    return (
        f"{path}: Linux camera backend={backend!r}, "
        f"cam_id={device_id}, {width}x{height} at {fps} FPS"
    )


def build_checks(
    config_path: Path,
    require_overlay: bool,
) -> tuple[tuple[str, Callable[[], str]], ...]:
    display_name = os.environ.get("DISPLAY")
    return (
        ("Python", lambda: check_python(sys.version_info)),
        (
            "Platform",
            lambda: check_platform(
                sys.platform,
                platform.freedesktop_os_release(),
                platform.machine(),
            ),
        ),
        ("Xorg session", lambda: check_session(os.environ)),
        (
            "X11 display",
            lambda: _check_x11_display(display_name),
        ),
        (
            "XTest",
            lambda: check_x11_extension(
                display_name,
                _query_x11_extensions(display_name),
                "XTEST",
            ),
        ),
        (
            "XFixes",
            lambda: check_x11_extension(
                display_name,
                _query_x11_extensions(display_name),
                "XFIXES",
            ),
        ),
        (
            "X11 compositor",
            lambda: check_compositor(
                _load_config(config_path),
                require_overlay,
                _compositor_owner_exists(display_name),
            ),
        ),
        ("Configuration", lambda: _check_config(config_path)),
        (
            "Model assets",
            lambda: check_model_assets(
                _load_config(config_path),
                REPOSITORY_ROOT,
            ),
        ),
        ("Orbbec binding/SDK ABI", _check_orbbec_abi_host),
        (
            "Selected camera",
            lambda: check_camera_selection(
                _load_config(config_path),
                sys.platform,
            ),
        ),
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check NeuGaze Ubuntu/Xorg prerequisites without changing "
            "the host"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/cpu.yaml"),
        help="NeuGaze YAML configuration (default: configs/cpu.yaml)",
    )
    parser.add_argument(
        "--require-overlay",
        action="store_true",
        help="require an active X11 compositing manager",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    failures = execute_checks(
        build_checks(args.config, args.require_overlay),
        sys.stdout,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
