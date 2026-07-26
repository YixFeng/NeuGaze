# NeuGaze Ubuntu 24.04 Xorg Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status note:** This file is the historical execution template. Its checkboxes are not mechanically backfilled; current completion and fresh verification evidence are authoritative only in `docs/ubuntu-xorg-port-progress.md`.

**Goal:** Make the NeuGaze GUI production path run on Ubuntu 24.04 Xorg with explicit Orbbec Gemini 335 and OpenCV/V4L2 camera backends, full X11 input control, and a click-through gaze overlay while preserving Windows behavior.

**Architecture:** Add one direct camera boundary and one narrow desktop package. Camera and desktop selection are explicit `if/elif` branches with no capability probing or fallback; inference remains platform-neutral. Keep the Win32 overlay and add an Xorg PySide6 overlay process selected by a small import module.

**Tech Stack:** Python 3.11, pytest, PyTorch 2.6 CPU, OpenCV, PySide6, python-xlib/XTest/XFixes, pyorbbecsdk2 2.1.1, Xvfb, xcompmgr.

## Global Constraints

- Target Ubuntu is Ubuntu 24.04 x86-64 under Xorg; Wayland is unsupported and must fail fast.
- Preserve Windows OpenCV/DirectShow and Win32 behavior.
- Ubuntu camera backends are explicitly `orbbec` or `opencv`; neither may call the other after failure.
- Default Linux camera is Orbbec Gemini 335 RGB at 1280x720 and 30 FPS; depth and IR remain disabled.
- Runtime must not use root. Ask the user before any installation-time `sudo`.
- Do not migrate `learn/`.
- Do not add silent fallbacks, retry loops, cached frames, or false success states.
- Preserve original exceptions and tracebacks across thread/process boundaries.
- Update `docs/ubuntu-xorg-port-progress.md` after every task changes state or verification evidence.

---

## File Structure

- Create `my_model_arch/cpu_fast/camera.py`: camera config resolution, enumeration, OpenCV/V4L2 source, and Orbbec RGB source.
- Create `my_model_arch/cpu_fast/desktop/__init__.py`: explicit platform selector and public function exports.
- Create `my_model_arch/cpu_fast/desktop/win32.py`: current Win32 key map, key/mouse injection, state, screen, pointer, and cursor visibility.
- Create `my_model_arch/cpu_fast/desktop/x11.py`: X11 connection validation, XKB resolution, XTest injection, XFixes cursor state, and held-input cleanup.
- Modify `my_model_arch/cpu_fast/keyboard_utils.py`: retain only platform-neutral `Action`, `OpType`, and safe key semantics.
- Modify `my_model_arch/cpu_fast/eye_gaze_mouse_control.py`: retain movement algorithms and delegate system operations to `desktop`.
- Create `my_model_arch/cpu_fast/gaze_overlay.py`: explicit overlay selector.
- Create `my_model_arch/cpu_fast/gaze_overlay_x11.py`: supervised PySide6 overlay process.
- Modify `my_model_arch/cpu_fast/gaze_show_utils.py`: Win32 overlay only; remove silent lifecycle catches touched by this work.
- Modify `my_model_arch/cpu_fast/utils.py`: remove Win32 cursor code after consumers move to `desktop`.
- Modify `my_model_arch/cpu_fast/pipeline.py`: consume camera, desktop, neutral actions, and selected overlay; make worker and cleanup errors observable.
- Modify `config_gui_cpu.py`: camera backend/device controls, config roundtrip, selected source preview, and desktop hotkeys.
- Modify `configs/cpu.yaml`: explicit per-platform backend and camera stream fields.
- Create `requirements-ubuntu.txt`: Ubuntu CPU/runtime dependencies.
- Create `requirements-dev.txt`: test dependencies.
- Create `pytest.ini`: strict test configuration and integration markers.
- Create `scripts/check_ubuntu_runtime.py`: read-only environment/SDK/X11 diagnostic.
- Modify `README.md` and `README-CN.md`: exact Ubuntu install, Xorg, camera selection, diagnostics, and run instructions.
- Create tests under `tests/` matching the task sections below.

### Task 1: Test Harness and Explicit Camera Configuration

**Files:**
- Create: `pytest.ini`
- Create: `requirements-dev.txt`
- Create: `my_model_arch/cpu_fast/camera.py`
- Create: `tests/test_camera_config.py`
- Modify: `configs/cpu.yaml:34-58`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Produces: `CameraConfig`, `resolve_camera_backend(camera_backend, platform)`, and `camera_config_from_mapping(integrated_config, platform)`.
- `CameraConfig` fields: `backend: str`, `device_id: int`, `width: int`, `height: int`, `fps: int`.

- [ ] **Step 1: Add the strict pytest configuration and failing config tests**

```ini
# pytest.ini
[pytest]
testpaths = tests
addopts = -ra --strict-markers
markers =
    x11: requires an isolated X11 display
    hardware: requires explicitly selected camera hardware
```

```text
# requirements-dev.txt
pytest==8.4.1
```

```python
# tests/test_camera_config.py
import pytest

from my_model_arch.cpu_fast.camera import (
    CameraConfig,
    camera_config_from_mapping,
    resolve_camera_backend,
)


def test_resolve_camera_backend_is_platform_explicit():
    configured = {"linux": "orbbec", "win32": "opencv"}
    assert resolve_camera_backend(configured, "linux") == "orbbec"
    assert resolve_camera_backend(configured, "win32") == "opencv"


@pytest.mark.parametrize("configured", [{}, {"linux": "auto"}, "orbbec", None])
def test_resolve_camera_backend_rejects_missing_or_implicit_values(configured):
    with pytest.raises((TypeError, ValueError)):
        resolve_camera_backend(configured, "linux")


def test_camera_config_reads_exact_stream_values():
    mapping = {
        "camera_backend": {"linux": "opencv", "win32": "opencv"},
        "cam_id": 2,
        "camera_width": 1280,
        "camera_height": 720,
        "camera_fps": 30,
    }
    assert camera_config_from_mapping(mapping, "linux") == CameraConfig(
        backend="opencv", device_id=2, width=1280, height=720, fps=30
    )


@pytest.mark.parametrize("field,value", [
    ("cam_id", -1), ("camera_width", 0), ("camera_height", 0), ("camera_fps", 0)
])
def test_camera_config_rejects_invalid_numeric_values(field, value):
    mapping = {
        "camera_backend": {"linux": "orbbec", "win32": "opencv"},
        "cam_id": 0,
        "camera_width": 1280,
        "camera_height": 720,
        "camera_fps": 30,
    }
    mapping[field] = value
    with pytest.raises(ValueError, match=field):
        camera_config_from_mapping(mapping, "linux")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v`

Expected: collection fails with `ModuleNotFoundError: No module named 'my_model_arch.cpu_fast.camera'`.

- [ ] **Step 3: Implement the exact config boundary**

```python
# my_model_arch/cpu_fast/camera.py
from dataclasses import dataclass
from typing import Mapping


VALID_CAMERA_BACKENDS = frozenset({"orbbec", "opencv"})


@dataclass(frozen=True)
class CameraConfig:
    backend: str
    device_id: int
    width: int
    height: int
    fps: int


def resolve_camera_backend(camera_backend: Mapping[str, str], platform: str) -> str:
    if not isinstance(camera_backend, Mapping):
        raise TypeError("integrated_config.camera_backend must be a platform mapping")
    if platform not in camera_backend:
        raise ValueError(f"camera_backend has no explicit value for platform {platform!r}")
    backend = camera_backend[platform]
    if backend not in VALID_CAMERA_BACKENDS:
        raise ValueError(
            f"camera_backend[{platform!r}] must be one of "
            f"{sorted(VALID_CAMERA_BACKENDS)}, got {backend!r}"
        )
    if platform == "win32" and backend != "opencv":
        raise ValueError("Windows camera_backend must remain 'opencv'")
    return backend


def camera_config_from_mapping(
    integrated_config: Mapping[str, object], platform: str
) -> CameraConfig:
    backend = resolve_camera_backend(integrated_config["camera_backend"], platform)
    values = {}
    for field in ("cam_id", "camera_width", "camera_height", "camera_fps"):
        value = integrated_config[field]
        if not isinstance(value, int) or value < 0 or (field != "cam_id" and value == 0):
            requirement = "a non-negative integer" if field == "cam_id" else "a positive integer"
            raise ValueError(f"{field} must be {requirement}")
        values[field] = value
    return CameraConfig(
        backend=backend,
        device_id=values["cam_id"],
        width=values["camera_width"],
        height=values["camera_height"],
        fps=values["camera_fps"],
    )
```

Add under `integrated_config` in `configs/cpu.yaml`:

```yaml
  camera_backend:
    linux: orbbec
    win32: opencv
  camera_width: 1280
  camera_height: 720
  camera_fps: 30
```

- [ ] **Step 4: Run GREEN and record progress**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v`

Expected: all camera config tests pass.

Update the progress table to mark Task 1 complete and append the command/result.

- [ ] **Step 5: Commit**

```bash
git add pytest.ini requirements-dev.txt my_model_arch/cpu_fast/camera.py tests/test_camera_config.py configs/cpu.yaml docs/ubuntu-xorg-port-progress.md
git commit -m "test: define explicit camera configuration"
```

### Task 2: Fail-Fast OpenCV/V4L2 and Orbbec RGB Sources

**Files:**
- Modify: `my_model_arch/cpu_fast/camera.py`
- Create: `tests/test_camera_sources.py`
- Create: `tests/test_orbbec_hardware.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Produces: `CameraInfo(backend, device_id, label, serial)`, `OpenCVCamera`, `OrbbecColorCamera`, `list_cameras(backend, platform)`, and `open_camera(config, platform)`.
- Both source classes expose `read() -> numpy.ndarray` and `close() -> None`; they never return status tuples.

- [ ] **Step 1: Write failing behavioral tests**

Create fakes that implement the concrete OpenCV methods (`isOpened`, `set`, `get`, `read`, `release`) and Orbbec methods (`query_devices`, `get_video_stream_profile`, `start`, `wait_for_frames`, `stop`). Add these tests:

```python
def test_open_camera_does_not_fallback_after_v4l2_failure(monkeypatch):
    called = []
    monkeypatch.setattr(camera, "_open_opencv", lambda config, platform: called.append("opencv") or (_ for _ in ()).throw(RuntimeError("v4l2 failed")))
    monkeypatch.setattr(camera, "_open_orbbec", lambda config: called.append("orbbec"))
    with pytest.raises(RuntimeError, match="v4l2 failed"):
        camera.open_camera(CameraConfig("opencv", 0, 1280, 720, 30), "linux")
    assert called == ["opencv"]


def test_opencv_read_rejects_empty_frame():
    source = OpenCVCamera(
        FakeCapture(read_result=(False, None)),
        CameraConfig("opencv", 0, 1280, 720, 30),
        backend_name="V4L2",
    )
    with pytest.raises(RuntimeError, match="V4L2 camera 0 failed to read a frame"):
        source.read()


def test_orbbec_rgb_is_converted_to_contiguous_bgr():
    rgb = np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
    source = OrbbecColorCamera.from_pipeline(FakeOrbbecPipeline(rgb), device_label="Gemini 335 SN123", width=2, height=1, fps=30)
    bgr = source.read()
    assert bgr.tolist() == [[[3, 2, 1], [6, 5, 4]]]
    assert bgr.flags.c_contiguous


def test_orbbec_timeout_is_an_error_not_an_empty_frame():
    source = OrbbecColorCamera.from_pipeline(FakeOrbbecPipeline(None), device_label="Gemini 335 SN123", width=1280, height=720, fps=30)
    with pytest.raises(TimeoutError, match="1000 ms"):
        source.read()
```

Also test: negotiated V4L2 size/FPS mismatch, wrong dtype/shape, double close, Orbbec missing color frame, wrong byte length, and `orbbec` failure never invokes OpenCV.

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_sources.py -v`

Expected: imports fail because source classes and open/list functions do not exist.

- [ ] **Step 3: Implement the two direct sources**

Implement these exact signatures:

Define these concrete interfaces:

- `CameraInfo` is a frozen dataclass with `backend: str`, `device_id: int`, `label: str`, and optional `serial: str` fields.
- `OpenCVCamera.__init__(capture, config: CameraConfig, backend_name: str)` owns one already-open capture.
- `OpenCVCamera.open(config: CameraConfig, platform: str) -> OpenCVCamera` selects exactly one platform API and either returns it or raises.
- `OpenCVCamera.read() -> np.ndarray` returns one validated BGR frame.
- `OpenCVCamera.close() -> None` releases the capture.
- `OrbbecColorCamera.open(config: CameraConfig) -> OrbbecColorCamera` selects the configured SDK device and exact RGB profile.
- `OrbbecColorCamera.from_pipeline(pipeline, device_label: str, width: int, height: int, fps: int) -> OrbbecColorCamera` is the test seam for an already-created pipeline.
- `OrbbecColorCamera.read() -> np.ndarray` returns one validated contiguous BGR frame.
- `OrbbecColorCamera.close() -> None` stops the pipeline.

Use this explicit dispatcher:

```python
def list_cameras(backend: str, platform: str) -> list[CameraInfo]:
    if backend == "orbbec":
        return _list_orbbec()
    if backend == "opencv":
        return _list_opencv(platform)
    raise ValueError(f"unsupported camera backend: {backend!r}")


def open_camera(config: CameraConfig, platform: str):
    if config.backend == "orbbec":
        return OrbbecColorCamera.open(config)
    if config.backend == "opencv":
        return OpenCVCamera.open(config, platform)
    raise ValueError(f"unsupported camera backend: {config.backend!r}")
```

Rules inside the bodies:

- Import `pyorbbecsdk` only inside Orbbec functions.
- Linux OpenCV uses only `cv2.CAP_V4L2`; Windows uses only `cv2.CAP_DSHOW`.
- Check every `capture.set` return and negotiated `CAP_PROP_*` value.
- `read()` raises on false status, `None`, non-`uint8`, non-HWC/3-channel frame, or mismatched configured size.
- Request the exact Orbbec RGB profile and use `Pipeline(device)`.
- Use `wait_for_frames(1000)`, require a color frame, validate data length, reshape it, call `cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)`, and then `np.ascontiguousarray(bgr)`.
- `close()` is idempotent only after a successful first close; if the underlying first close fails, propagate it and keep the source open for an explicit later cleanup attempt.

- [ ] **Step 4: Run unit GREEN**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py tests/test_camera_sources.py -v`

Expected: all tests pass with no warnings.

- [ ] **Step 5: Add the explicit hardware test**

`tests/test_orbbec_hardware.py` must require `--run-orbbec` registered in `tests/conftest.py`. When selected, assert the label contains `Gemini 335`, read 100 valid `(720, 1280, 3)` BGR frames, close, reopen, and read one more frame. When not selected, deselect at collection; when selected and missing, fail rather than skip.

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v`

Expected with connected hardware: PASS. If the binding or permission is missing: FAIL with the original Orbbec error; record that exact blocker in the progress document.

- [ ] **Step 6: Commit**

```bash
git add my_model_arch/cpu_fast/camera.py tests/test_camera_sources.py tests/test_orbbec_hardware.py tests/conftest.py docs/ubuntu-xorg-port-progress.md
git commit -m "feat: add explicit Ubuntu camera sources"
```

### Task 3: Platform-Neutral Actions and Explicit Desktop Selection

**Files:**
- Create: `my_model_arch/cpu_fast/desktop/__init__.py`
- Create: `my_model_arch/cpu_fast/desktop/win32.py`
- Create: `tests/test_desktop_selection.py`
- Create: `tests/test_keyboard_actions.py`
- Modify: `my_model_arch/cpu_fast/keyboard_utils.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Desktop exports `initialize`, `close`, `get_screen_size`, `get_pointer_position`, `move_pointer`, `key_down`, `key_up`, `key_up_owned`, `is_key_down`, `are_keys_down`, `supports_key`, `scroll`, `is_cursor_visible`, and `release_all`.
- `keyboard_utils.Action.execute()` delegates synchronously to these exports.

- [ ] **Step 1: Write selector and action tests**

Use an injected fake module to assert selection exports one backend and never imports the other. Test every `OpType`, unknown keys, safe-down false when already held, owned-only safe-up single release and sync, unowned safe-up with zero events, ownership retention after release or sync failure for explicit retry, and action exception propagation.

```python
def test_action_propagates_backend_error(monkeypatch):
    monkeypatch.setattr(keyboard_utils.desktop, "key_down", lambda key: (_ for _ in ()).throw(OSError("injection failed")))
    with pytest.raises(OSError, match="injection failed"):
        Action("w", OpType.KEYDOWN).execute()
```

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_desktop_selection.py tests/test_keyboard_actions.py -v`

Expected: missing `desktop` package.

- [ ] **Step 3: Move the Win32 primitives and simplify keyboard_utils**

`desktop/__init__.py` validates the operating system immediately but loads the concrete backend only on first use, so Task 3 remains importable before Task 4 adds X11:

```python
import sys
from importlib import import_module

if sys.platform == "win32":
    _BACKEND_MODULE = "my_model_arch.cpu_fast.desktop.win32"
elif sys.platform.startswith("linux"):
    _BACKEND_MODULE = "my_model_arch.cpu_fast.desktop.x11"
else:
    raise RuntimeError(f"NeuGaze does not support desktop platform {sys.platform!r}")

_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        _backend = import_module(_BACKEND_MODULE)
    return _backend


def initialize(): return _get_backend().initialize()
def get_screen_size(): return _get_backend().get_screen_size()
def get_pointer_position(): return _get_backend().get_pointer_position()
def move_pointer(x, y, relative=False):
    return _get_backend().move_pointer(x, y, relative=relative)
def key_down(key): return _get_backend().key_down(key)
def key_up(key): return _get_backend().key_up(key)
def key_up_owned(key): return _get_backend().key_up_owned(key)
def is_key_down(key): return _get_backend().is_key_down(key)
def are_keys_down(keys): return _get_backend().are_keys_down(keys)
def supports_key(key): return _get_backend().supports_key(key)
def scroll(steps): return _get_backend().scroll(steps)
def is_cursor_visible(): return _get_backend().is_cursor_visible()
def release_all(): return _get_backend().release_all()


def close():
    global _backend
    if _backend is not None:
        _backend.close()
        _backend = None
```

Move the existing Win32 `KEY_MAP` and API calls into `desktop/win32.py`, adding held-input tracking and `release_all()`. Replace silent `GetCursorInfo` success defaults with `ctypes.WinError(ctypes.get_last_error())`.

Replace `keyboard_utils.py` with the existing `OpType`/`Action` dataclass plus these platform-neutral functions:

```python
def keydown(key): desktop.key_down(key)
def keyup(key): desktop.key_up(key)
def keypress(key, duration=0.01):
    desktop.key_down(key)
    time.sleep(duration)
    desktop.key_up(key)
def is_key_down(key): return desktop.is_key_down(key)
def keydown_safe(key):
    if desktop.is_key_down(key):
        return False
    desktop.key_down(key)
    return True
def keyup_safe(key):
    return desktop.key_up_owned(key)
```

Delete the unused Raw Input hook and all top-level Win32 imports from `keyboard_utils.py`.

- [ ] **Step 4: Run GREEN and compile common modules**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_desktop_selection.py tests/test_keyboard_actions.py -v`

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile my_model_arch/cpu_fast/keyboard_utils.py my_model_arch/cpu_fast/desktop/__init__.py my_model_arch/cpu_fast/desktop/win32.py`

Expected: tests pass and compilation exits 0.

- [ ] **Step 5: Commit**

```bash
git add my_model_arch/cpu_fast/desktop my_model_arch/cpu_fast/keyboard_utils.py tests/test_desktop_selection.py tests/test_keyboard_actions.py docs/ubuntu-xorg-port-progress.md
git commit -m "refactor: isolate desktop input operations"
```

### Task 4: X11/XTest/XFixes Backend

**Files:**
- Create: `my_model_arch/cpu_fast/desktop/x11.py`
- Create: `tests/test_x11_keymap.py`
- Create: `tests/test_x11_integration.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Implements every export named in Task 3.
- Adds no alternative backend and opens no Display connection at import time.

- [ ] **Step 1: Write failing pure keymap tests**

Test letters, digits, F1-F12, modifiers, navigation, numpad, punctuation, mouse buttons, X1/X2, unknown names, and required Shift levels. Use a fake keyboard mapping with exact keycodes; assert the resolved `(keycode, modifiers)` tuple.

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_keymap.py -v`

Expected: `desktop.x11` is missing or required functions are undefined.

- [ ] **Step 3: Implement X11 lifecycle and key resolution**

Use module-level `_display`, `_root`, `_lock = threading.RLock()`, `_held_keys`, and `_held_buttons`. `initialize()` must:

- reject `XDG_SESSION_TYPE=wayland`;
- require non-empty `DISPLAY`;
- connect with `Xlib.display.Display`;
- require `XTEST` and `XFIXES` in `list_extensions()`;
- set `_root` only after every check succeeds.

Map named keys to X keysyms; resolve printable one-character keys from the active keyboard mapping and return the Shift modifier when found at level 1. Unknown/unavailable symbols raise `ValueError` with the name and display string.

- [ ] **Step 4: Implement XTest operations and XFixes cursor state**

- Pointer absolute: `xtest.fake_input(display, X.MotionNotify, x=x, y=y)`.
- Pointer relative: query root pointer, add deltas, then send absolute motion.
- Buttons: 1/2/3/8/9; scroll uses press/release of 4 or 5 per step.
- Key state: inspect `query_keymap()` bit for the resolved keycode.
- Cursor: call XFixes `GetCursorImage`, require width/height/pixel count, and return whether any pixel has a nonzero top-byte Alpha.
- Every mutating call flushes; every operation requires initialized state.
- `release_all()` releases only entries recorded in `_held_keys`/`_held_buttons`; aggregate cleanup failures and raise one `ExceptionGroup`.

- [ ] **Step 5: Run pure GREEN**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_keymap.py -v`

Expected: all keymap/cursor parsing tests pass.

- [ ] **Step 6: Add and run Xvfb integration**

`tests/test_x11_integration.py` starts no server itself. Execute it under:

```bash
xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_integration.py -m x11 -v
```

Tests initialize/close, move/query pointer, key down/query/up, button press/release, scroll, unknown key errors, and Wayland rejection in a subprocess.

Expected: all integration tests pass. If `xvfb-run` is absent, record it and request approval before installing `xvfb`; do not skip.

- [ ] **Step 7: Commit**

```bash
git add my_model_arch/cpu_fast/desktop/x11.py tests/test_x11_keymap.py tests/test_x11_integration.py docs/ubuntu-xorg-port-progress.md
git commit -m "feat: implement X11 desktop control"
```

### Task 5: Connect Camera and Desktop to the Production Pipeline

**Files:**
- Modify: `my_model_arch/cpu_fast/eye_gaze_mouse_control.py`
- Modify: `my_model_arch/cpu_fast/utils.py:264-307`
- Modify: `my_model_arch/cpu_fast/pipeline.py:13-50,193-325,1152-1170,1253-1470,2248-2780`
- Create: `tests/test_gaze_mouse_controller.py`
- Create: `tests/test_pipeline_runtime.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- `GazeMouseController.raise_if_failed() -> None`.
- Pipeline constructor consumes `camera_backend`, `camera_width`, `camera_height`, `camera_fps`.
- Pipeline source field is `self.camera`; it exposes `read()` and `close()`.

- [ ] **Step 1: Write failing controller and pipeline tests**

Test visible cursor absolute movement, hidden cursor relative movement, head movement, worker exception storage/rethrow, camera open once, read exception propagation, and close during quit.

```python
def test_controller_rethrows_worker_failure(monkeypatch, observer):
    monkeypatch.setattr(desktop, "is_cursor_visible", lambda: (_ for _ in ()).throw(OSError("XFixes failed")))
    controller = GazeMouseController(observer)
    controller.start()
    controller.update_gaze(100, 100)
    wait_until_worker_stops(controller)
    with pytest.raises(OSError, match="XFixes failed"):
        controller.raise_if_failed()
```

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py -v`

Expected: current top-level Win32 imports fail and runtime interfaces are missing.

- [ ] **Step 3: Refactor GazeMouseController**

Remove `win32api`, `win32con`, `WinDLL`, `GetCursorInfo`, and `pyautogui`. Use:

- `desktop.move_pointer(int(x), int(y), relative=False)`;
- `desktop.move_pointer(int(dx), int(dy), relative=True)`;
- `desktop.get_pointer_position()`;
- `desktop.is_cursor_visible()`.

Catch only at the outer worker boundary, store `sys.exc_info()`, stop the worker, and implement:

```python
def raise_if_failed(self):
    if self._worker_error is None:
        return
    exc_type, exc, traceback = self._worker_error
    raise exc.with_traceback(traceback)
```

Catch `queue.Empty` explicitly instead of bare `except`.

- [ ] **Step 4: Refactor pipeline camera, desktop, hotkeys, and actions**

- Replace Win32 screen methods with `desktop.get_screen_size()`.
- Build `CameraConfig` once in `__init__`, and call `open_camera` from `start_service`.
- Change `cap_read_img` to `self.frame = self.camera.read()`; remove status-tuple/`None` spinning.
- Replace `keyboard.is_pressed` with `desktop.are_keys_down(("esc", "q"))` and analogous R/T combinations.
- Replace `KEY_MAP` membership with `desktop.supports_key(action_key)`.
- Replace `pyautogui.hotkey/scroll` with explicit desktop key down/up and `desktop.scroll`.
- Execute `Action.execute()` synchronously in the existing action loop.
- Call controller `raise_if_failed()` every evaluation iteration.
- In `quit_pipeline`, preserve a primary error, call `desktop.release_all`, controller stop, camera close, and window cleanup, then raise cleanup failures as `ExceptionGroup` if no primary error exists.

Remove the Win32 cursor block from `utils.py`.

- [ ] **Step 5: Run GREEN and regression tests**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`

Expected: all pass, no unhandled thread warnings.

- [ ] **Step 6: Commit**

```bash
git add my_model_arch/cpu_fast/eye_gaze_mouse_control.py my_model_arch/cpu_fast/utils.py my_model_arch/cpu_fast/pipeline.py tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py docs/ubuntu-xorg-port-progress.md
git commit -m "refactor: connect production pipeline to platform services"
```

### Task 6: Supervised Xorg Gaze Overlay

**Files:**
- Create: `my_model_arch/cpu_fast/gaze_overlay.py`
- Create: `my_model_arch/cpu_fast/gaze_overlay_x11.py`
- Modify: `my_model_arch/cpu_fast/gaze_show_utils.py`
- Modify: `my_model_arch/cpu_fast/pipeline.py:36,2312-2358,2444-2460`
- Create: `tests/test_gaze_overlay_process.py`
- Create: `tests/test_gaze_overlay_x11.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Both platform classes expose `start()`, `update_gaze_position(x, y)`, `raise_if_failed()`, and `stop()`.

- [ ] **Step 1: Write failing supervision tests**

Test ready handshake, child traceback transfer, unexpected child death, latest-coordinate coalescing, stop acknowledgement, and stop timeout.

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_overlay_process.py -v`

Expected: selected overlay modules are missing.

- [ ] **Step 3: Implement explicit selection and child protocol**

`gaze_overlay.py` imports Win32 only on `win32`, X11 only on Linux, and raises elsewhere.

`gaze_overlay_x11.py` uses `multiprocessing.get_context("spawn")`, one duplex control `Pipe`, and one point `Queue(maxsize=1)`. Control messages are exact tuples:

- child → parent: `("ready", None)`
- parent → child: `("stop", None)`
- child → parent: `("stopped", None)`
- child → parent: `("error", formatted_traceback)`

The parent publishes `(x, y)` to the point queue. When it is full, the parent removes the stale coordinate and immediately inserts the newest one. The child creates one `QApplication`, a frameless full-screen `QWidget` with `WA_TranslucentBackground`, `WindowStaysOnTopHint`, `WindowTransparentForInput`, and `WindowDoesNotAcceptFocus`. `paintEvent` draws the configured Gaussian-like radial gradient and history. A `QTimer` polls control messages, drains the point queue, and repaints only the newest coordinate. Control messages are never discarded or mixed with point traffic.

Before ready, require an owner for `_NET_WM_CM_S0`; absence raises `RuntimeError("X11 compositing manager is required for gaze overlay")`.

- [ ] **Step 4: Make lifecycle failures observable**

Parent `start()` waits at most 5 seconds for ready/error. `update_gaze_position` replaces an unsent stale point in the bounded queue before publishing the latest. `raise_if_failed()` reports child errors/death. `stop()` waits 5 seconds for stopped and process exit; timeout raises and does not pretend success.

Add `raise_if_failed()` to the Win32 overlay. Replace touched `except: pass` lifecycle branches with explicit “class not found” handling or raised errors.

- [ ] **Step 5: Integrate without a parent gaze thread**

In `RealAction.start_gaze_display`, start the overlay only. In `call_after_each_eval_loop`, update the current predicted position and call `raise_if_failed`. In stop, stop the overlay synchronously. Remove `gaze_thread` and `gaze_running`.

- [ ] **Step 6: Run unit and Xvfb+compositor GREEN**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_overlay_process.py -v`

Run:

```bash
xvfb-run -a sh -c 'xcompmgr -a & /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_overlay_x11.py -m x11 -v'
```

Expected: process tests and transparent overlay handshake tests pass. If `xcompmgr` is absent, request approval before installing it.

- [ ] **Step 7: Commit**

```bash
git add my_model_arch/cpu_fast/gaze_overlay.py my_model_arch/cpu_fast/gaze_overlay_x11.py my_model_arch/cpu_fast/gaze_show_utils.py my_model_arch/cpu_fast/pipeline.py tests/test_gaze_overlay_process.py tests/test_gaze_overlay_x11.py docs/ubuntu-xorg-port-progress.md
git commit -m "feat: add supervised Xorg gaze overlay"
```

### Task 7: GUI Camera Backend, Preview, and Config Roundtrip

**Files:**
- Modify: `config_gui_cpu.py:13-30,335-365,608-905,949-976,1132-1170,1337-1440,1593-1950,2107-2237`
- Create: `tests/test_config_gui_camera.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- GUI stores `self.camera_config`, `self.camera`, `self.camera_backend_combo`, and `self.camera_combo`.
- GUI uses `list_cameras`, `open_camera`, and `desktop.are_keys_down`.

- [ ] **Step 1: Write failing Qt GUI tests**

Using a real `QApplication` with `QT_QPA_PLATFORM=offscreen`, test:

- Linux backend combo defaults to Orbbec from YAML.
- Switching to OpenCV closes the prior preview before enumeration.
- Device labels retain backend/device IDs.
- Preview displays a supplied BGR frame.
- Backend open/read exceptions appear in `QMessageBox.critical` with traceback and leave buttons disabled.
- Saving changes only `camera_backend["linux"]` and preserves `win32: opencv`.
- Loading unknown/missing platform backend fails.
- Hotkey checks delegate to desktop.

- [ ] **Step 2: Run RED**

Run: `QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_config_gui_camera.py -v`

Expected: backend widgets and camera APIs are missing.

- [ ] **Step 3: Replace camera enumeration and preview**

- Remove top-level `keyboard`.
- Add backend combo before device combo.
- Resolve the current platform value from YAML.
- `list_cameras` populates model/serial labels for Orbbec and `/dev/videoN` labels for V4L2.
- `on_camera_selected` creates the selected source with `open_camera`.
- `update_preview` consumes the returned BGR ndarray directly.
- `confirm_camera_selection` writes backend/device/width/height/FPS.
- `restart_camera_preview` uses the same selected backend; no DirectShow on Linux.
- Calibration/evaluation close preview before pipeline ownership.

- [ ] **Step 4: Make the GUI the visible error boundary**

Replace `initialize_pipeline` boolean failure with an exception-preserving boundary: format `traceback.format_exc()`, show it once, keep `self.pipeline = None`, disable start buttons, and re-raise in tests. Do not continue to the alternate backend.

- [ ] **Step 5: Run GREEN**

Run: `QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_config_gui_camera.py tests/test_camera_config.py tests/test_camera_sources.py -v`

Expected: all pass with no Qt warnings.

- [ ] **Step 6: Commit**

```bash
git add config_gui_cpu.py tests/test_config_gui_camera.py docs/ubuntu-xorg-port-progress.md
git commit -m "feat: expose explicit camera backends in GUI"
```

### Task 8: Ubuntu Dependencies, Diagnostics, Documentation, and Full Verification

**Files:**
- Create: `requirements-ubuntu.txt`
- Create: `scripts/check_ubuntu_runtime.py`
- Create: `tests/test_ubuntu_requirements.py`
- Modify: `README.md`
- Modify: `README-CN.md`
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Diagnostic exits 0 only when exact Python 3.11.11, exact case-normalized Xorg session type `x11`, XTest, XFixes, optional compositor, Orbbec binding/SDK ABI, model assets, and selected camera prerequisites are valid.
- 2026-07-26 approved ABI resolution: obtain one `pyorbbecsdk2` `Distribution`; use its version and its unique `files`/`locate_file` `pyorbbecsdk/__init__.py` package root; require that canonical root to equal the actual imported module package root; require SDK API `2.8.6` and `libOrbbecSDK.so.2` to resolve strictly inside and exactly to the expected target under that same package. System SDK 2.9.3 is informational only and must never become the Python runtime library.
- 2026-07-26 approved OpenCV Option B: the final environment has only `opencv-contrib-python==4.11.0.86` ownership of `cv2`. A normal requirements install is immediately followed by uninstalling transitively pulled `opencv-python` and force-reinstalling contrib with `--no-deps`. The exact two-line upstream distribution-name failure from `pip check` is visible and approved; it is never filtered or reported as passed.

- [ ] **Step 1: Write diagnostic tests first**

Create `tests/test_ubuntu_runtime_check.py` covering success plus wrong Python patch, every non-`x11` session value, absent DISPLAY, missing XTest/XFixes, missing compositor when gaze display is enabled, missing model files, mismatched Orbbec library resolution, and a shadow import whose package root differs from the installed `Distribution` root. Create `tests/test_ubuntu_requirements.py` covering the exact direct distribution set, contrib-only OpenCV ownership, and the EN/CN post-install repair contract.

- [ ] **Step 2: Run RED**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_ubuntu_runtime_check.py -v`

Expected: diagnostic module is missing.

- [ ] **Step 3: Add pinned Ubuntu requirements**

`requirements-ubuntu.txt` must contain the existing common runtime packages, exclude `pywin32`, `keyboard`, `pyautogui`, and CUDA wheels, and pin:

```text
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.6.0+cpu
torchvision==0.21.0+cpu
torchaudio==2.6.0+cpu
opencv-contrib-python==4.11.0.86
python-xlib==0.33
pyorbbecsdk2==2.1.1
```

Do not list `opencv-python`. `pyorbbecsdk2` and `ncnn` still pull that distribution transitively during a normal resolver run, so installation must immediately uninstall it and force-reinstall exact contrib with `--no-deps`. This restores contrib ownership of every overlapping `cv2` file without changing other packages. Keep `requirements.txt` as the Windows set.

- [ ] **Step 4: Implement read-only diagnostics**

The script accepts `--config configs/cpu.yaml` and `--require-overlay`. It prints one line per check, collects all failures, then exits 1 with the full list. It never installs, rewrites env vars, edits udev, cleans `sys.path`, or falls back. For the Orbbec extension, one `Distribution` object supplies both the binding version and installed package root; that root must exactly match the actual imported module root before printing `pyorbbecsdk.get_version()` and validating the `ldd`-resolved `libOrbbecSDK` inside it.

- [ ] **Step 5: Run diagnostic GREEN**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_ubuntu_runtime_check.py -v`

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python scripts/check_ubuntu_runtime.py --config configs/cpu.yaml --require-overlay`

Expected: unit tests pass. Runtime command either exits 0 or lists exact missing prerequisites. For any system package/udev requirement, update progress and ask before `sudo`.

- [ ] **Step 6: Update both READMEs**

Document exact commands:

```bash
conda create -n neugaze python=3.11.11
conda activate neugaze
python -m pip install -r requirements-ubuntu.txt
python -m pip uninstall -y opencv-python
python -m pip install --no-deps --force-reinstall opencv-contrib-python==4.11.0.86
python scripts/check_ubuntu_runtime.py --config configs/cpu.yaml --require-overlay
python config_gui_cpu.py
```

Document choosing “Ubuntu on Xorg” at login, Orbbec versus OpenCV/V4L2 selection, no fallback behavior, non-root runtime, and the explicit hardware test.

- [ ] **Step 7: Run the full automated suite**

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m "not hardware and not x11" -v`

Run: `xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m x11 -v`

Run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile config_gui_cpu.py my_model_arch/cpu_fast/*.py my_model_arch/cpu_fast/desktop/*.py scripts/check_ubuntu_runtime.py`

Run the exact-pin/contrib-only functional import check, then run: `/home/yixiao/miniconda3/envs/neugaze/bin/python -m pip check`.

Expected: all selected tests pass, compilation exits 0, all direct pins match, only `opencv-contrib-python==4.11.0.86` metadata owns an importable OpenCV 4.11.0 with working MediaPipe and Orbbec imports, and `pip check` exits 1 with exactly this user-approved upstream metadata exception:

```text
pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.
ncnn 1.0.20260526 requires opencv-python, which is not installed.
```

Do not filter these lines, install an alias/dummy distribution, edit installed metadata, retain both OpenCV wheels, or report `pip check` as passed.

- [ ] **Step 8: Run explicit real-session acceptance**

Under the current Xorg session:

1. Run the diagnostic.
2. Run Orbbec hardware tests with `--run-orbbec`.
3. Start GUI and confirm Gemini 335 label/serial and 100-frame preview.
4. Switch to OpenCV/V4L2 and confirm a V4L2 camera, if one is connected; a missing selected device must visibly fail without invoking Orbbec.
5. Complete nine-point calibration.
6. Verify gaze absolute/relative pointer movement, left/right/middle/X buttons, scroll, held/released keys, combinations, wheel selection, overlay click-through/topmost/no-focus, and ESC+Q cleanup.
7. Disconnect Gemini 335 during preview and confirm the original SDK error terminates the operation.
8. Confirm no runtime command used `sudo`.

Record every command, result, and any untestable hardware item in the progress document; do not mark an unexecuted item passed.

- [ ] **Step 9: Final commit**

```bash
git add requirements-ubuntu.txt scripts/check_ubuntu_runtime.py tests/test_ubuntu_runtime_check.py tests/test_ubuntu_requirements.py README.md README-CN.md docs/ubuntu-xorg-port-progress.md
git commit -m "docs: add Ubuntu Xorg setup and verification"
```

## Ubuntu 安装检查与管理员边界

用户必须从登录界面选择 **Ubuntu on Xorg**。安装顺序固定如下；只读安装
检查器必须先于 pip 安装和 runtime 诊断运行：

```bash
conda create -n neugaze python=3.11.11
conda activate neugaze
export NEUGAZE_ORBBEC_SDK_ROOT=/absolute/path/to/OrbbecSDK_v2
python scripts/check_ubuntu_install.py --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" --require-overlay
python -m pip install -r requirements-ubuntu.txt
python -m pip uninstall -y opencv-python
python -m pip install --no-deps --force-reinstall opencv-contrib-python==4.11.0.86
python scripts/check_ubuntu_runtime.py --config configs/cpu.yaml --require-overlay
```

`check_ubuntu_install.py` 只检查并聚合报告，不安装、不复制、不改权限、不重载
udev，也不搜索备用 SDK。缺少 runtime 系统包时，必须先取得用户明确批准：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends xcompmgr libxcb-cursor0
```

测试工具需要另行批准：

```bash
sudo apt-get install --no-install-recommends xvfb
```

udev 规则调整也必须单独批准，且只能使用显式 SDK root 中的 installer：

```bash
sudo "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/install_udev_rules.sh"
```

校验本身不使用 sudo：

```bash
sha256sum "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules"
cmp --silent "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules" /etc/udev/rules.d/99-obsensor-libusb.rules
python scripts/check_ubuntu_install.py --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" --require-overlay
```

`NEUGAZE_ORBBEC_SDK_ROOT` 只定义 udev installer 与规则的来源，不改变
`pyorbbecsdk2==2.1.1` wheel 及其 bundled SDK 2.8.6 权威运行时。日常
runtime 不使用 sudo；任何修复动作都在用户批准后由用户显式执行。

## Final Review Gate

Before claiming completion:

1. Read the design and map every requirement to a completed task.
2. Run `git diff --check` and `git status --short`.
3. Run the full automated, X11, diagnostic, and available hardware commands above.
4. Confirm the progress document contains the latest commit hashes and honest verification status.
5. Use `superpowers:verification-before-completion`.
6. Use `superpowers:requesting-code-review`.
