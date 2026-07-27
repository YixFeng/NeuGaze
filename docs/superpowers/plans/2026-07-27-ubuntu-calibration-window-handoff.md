# Ubuntu Calibration Window Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Ubuntu calibration visibly hand off from the Qt configuration window to a mapped fullscreen OpenCV window while preserving original failures and leaving Windows behavior unchanged.

**Architecture:** Keep OpenCV HighGUI calibration on the main thread. The Qt window performs a Linux-only hide/restore handoff around `pipeline.start_calibration()`, while the pipeline maps an initial frame before requesting fullscreen from Xorg.

**Tech Stack:** Python 3.11, PySide6, OpenCV HighGUI, NumPy, pytest, Xorg

## Global Constraints

- Only Linux/Ubuntu calibration behavior changes; Windows remains unchanged.
- Do not add a worker thread, subprocess, retry, camera-backend fallback, or silent fallback.
- Restore the Qt configuration window before showing a calibration error.
- Preserve the original exception identity, traceback, and existing error dialog.
- Keep Gemini 335 RGB at 1280×720@30 FPS and all recognition/training behavior unchanged.

---

### Task 1: Linux Qt-to-OpenCV calibration handoff

**Files:**
- Modify: `tests/test_config_gui_camera.py`
- Modify: `config_gui_cpu.py:1505-1533`

**Interfaces:**
- Consumes: `ConfigWindow.camera_platform: str`, `ConfigWindow.pipeline.start_calibration()`, and `QApplication.processEvents()`.
- Produces: Linux-only `ConfigWindow.hide()` before calibration and `ConfigWindow.show()` before success return or error reporting.

- [ ] **Step 1: Write the failing success and Windows-boundary tests**

Add tests that replace `window.hide`, `window.show`, and `QApplication.processEvents` with event recorders:

```python
def test_linux_calibration_hides_config_window_until_pipeline_returns(
    window_factory, monkeypatch
):
    events = []
    window, _ = window_factory()
    window.camera_platform = "linux"
    window.pipeline = SimpleNamespace(
        start_calibration=lambda: events.append("pipeline") or True
    )
    monkeypatch.setattr(window, "hide", lambda: events.append("hide"))
    monkeypatch.setattr(window, "show", lambda: events.append("show"))
    monkeypatch.setattr(
        QApplication,
        "processEvents",
        lambda: events.append("events"),
    )

    assert window.start_calibration() is True
    assert events == ["hide", "events", "pipeline", "show", "events"]


def test_windows_calibration_does_not_hide_config_window(
    window_factory, monkeypatch
):
    events = []
    window, _ = window_factory()
    window.camera_platform = "win32"
    window.pipeline = SimpleNamespace(
        start_calibration=lambda: events.append("pipeline") or True
    )
    monkeypatch.setattr(window, "hide", lambda: events.append("hide"))
    monkeypatch.setattr(window, "show", lambda: events.append("show"))

    assert window.start_calibration() is True
    assert events == ["pipeline"]
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_config_gui_camera.py \
-k 'linux_calibration_hides_config_window or windows_calibration_does_not_hide_config_window' -v
```

Expected: the Linux test fails because no `hide` or `show` event occurs; the Windows test passes.

- [ ] **Step 3: Add the Linux-only handoff**

In `ConfigWindow.start_calibration()`, after any needed pipeline initialization and immediately before `pipeline.start_calibration()`:

```python
linux_window_handoff = self.camera_platform == "linux"
if linux_window_handoff:
    self.hide()
    QApplication.processEvents()
try:
    try:
        result = self.pipeline.start_calibration()
    finally:
        if linux_window_handoff:
            self.show()
            QApplication.processEvents()
except Exception:
    formatted_traceback = traceback.format_exc()
    self._disable_camera_actions()
    QMessageBox.critical(self, "Calibration Error", formatted_traceback)
    raise
```

Keep the existing `QTimer.singleShot` and return value after this block.

- [ ] **Step 4: Write the failing exception-order test**

```python
def test_linux_calibration_restores_window_before_reporting_original_error(
    window_factory, monkeypatch
):
    events = []
    error = RuntimeError("calibration failed")
    window, _ = window_factory()
    window.camera_platform = "linux"

    def fail():
        events.append("pipeline")
        raise error

    window.pipeline = SimpleNamespace(start_calibration=fail)
    monkeypatch.setattr(window, "hide", lambda: events.append("hide"))
    monkeypatch.setattr(window, "show", lambda: events.append("show"))
    monkeypatch.setattr(
        QApplication,
        "processEvents",
        lambda: events.append("events"),
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda parent, title, text: events.append(("error", text)),
    )

    with pytest.raises(RuntimeError) as caught:
        window.start_calibration()

    assert caught.value is error
    assert events[:5] == ["hide", "events", "pipeline", "show", "events"]
    assert events[5][0] == "error"
    assert "RuntimeError: calibration failed" in events[5][1]
```

- [ ] **Step 5: Run the three handoff tests and verify GREEN**

Run the Step 2 command with `-k 'linux_calibration or windows_calibration'`.

Expected: all selected tests pass.

### Task 2: Map the OpenCV calibration frame before fullscreen

**Files:**
- Modify: `tests/test_pipeline_runtime.py`
- Modify: `my_model_arch/cpu_fast/pipeline.py:1263-1271`

**Interfaces:**
- Consumes: `IntegratedRegressionMediaPipeline.screen_size` as `(width, height)` and `window_name: str`.
- Produces: `setup_window()` that calls `namedWindow`, `imshow`, `waitKey(1)`, `moveWindow`, and `setWindowProperty` in that exact order.

- [ ] **Step 1: Write the failing OpenCV call-order test**

```python
def test_setup_window_maps_first_frame_before_requesting_fullscreen(monkeypatch):
    pipeline = _pipeline_without_constructor()
    pipeline.window_name = "track"
    pipeline.screen_size = (1280, 720)
    pipeline.open_windows = []
    events = []

    monkeypatch.setattr(
        pipeline_module.cv2,
        "namedWindow",
        lambda name, flags: events.append(("named", name, flags)),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "imshow",
        lambda name, frame: events.append(
            ("show", name, frame.shape, frame.dtype)
        ),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "waitKey",
        lambda delay: events.append(("wait", delay)) or -1,
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "moveWindow",
        lambda name, x, y: events.append(("move", name, x, y)),
    )
    monkeypatch.setattr(
        pipeline_module.cv2,
        "setWindowProperty",
        lambda name, prop, value: events.append(
            ("fullscreen", name, prop, value)
        ),
    )

    pipeline.setup_window()

    assert events == [
        ("named", "track", pipeline_module.cv2.WINDOW_NORMAL),
        ("show", "track", (720, 1280, 3), pipeline_module.np.dtype("uint8")),
        ("wait", 1),
        ("move", "track", 0, 0),
        (
            "fullscreen",
            "track",
            pipeline_module.cv2.WND_PROP_FULLSCREEN,
            pipeline_module.cv2.WINDOW_FULLSCREEN,
        ),
    ]
    assert pipeline.open_windows == ["track"]
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_pipeline_runtime.py::test_setup_window_maps_first_frame_before_requesting_fullscreen -v
```

Expected: FAIL because `setup_window()` currently requests fullscreen before `imshow`.

- [ ] **Step 3: Implement the mapped first frame**

Replace `setup_window()` with:

```python
def setup_window(self):
    screen_width, screen_height = self.screen_size
    first_frame = np.full(
        (screen_height, screen_width, 3),
        225,
        dtype=np.uint8,
    )
    cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(self.window_name, first_frame)
    cv2.waitKey(1)
    cv2.moveWindow(self.window_name, x=0, y=0)
    cv2.setWindowProperty(
        self.window_name,
        cv2.WND_PROP_FULLSCREEN,
        cv2.WINDOW_FULLSCREEN,
    )
    self.open_windows.append(self.window_name)
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command.

Expected: PASS.

### Task 3: Regression verification and progress record

**Files:**
- Modify: `docs/ubuntu-xorg-port-progress.md`

**Interfaces:**
- Consumes: Task 1 and Task 2 test results.
- Produces: a Chinese progress entry recording the root cause, RED/GREEN results, and remaining Gemini 335 manual calibration acceptance.

- [ ] **Step 1: Run focused regression tests**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_config_gui_camera.py tests/test_pipeline_runtime.py -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run syntax verification**

```bash
/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile \
config_gui_cpu.py my_model_arch/cpu_fast/pipeline.py
```

Expected: exit 0.

- [ ] **Step 3: Record progress**

Append a dated Chinese entry to `docs/ubuntu-xorg-port-progress.md` containing:

- reported symptom and confirmed synchronous-main-thread root cause;
- measured pipeline/camera/first-frame timings;
- Linux-only Qt hide/restore and OpenCV map-before-fullscreen behavior;
- exact focused test and compile results;
- explicit statement that final Gemini 335 calibration remains a user-visible manual acceptance item.

- [ ] **Step 4: Review the diff**

```bash
git diff --check
git status --short
git diff -- config_gui_cpu.py my_model_arch/cpu_fast/pipeline.py \
tests/test_config_gui_camera.py tests/test_pipeline_runtime.py \
docs/ubuntu-xorg-port-progress.md
```

Expected: only the planned source, test, and progress files are modified; generated `Log/` remains outside the commit.

- [ ] **Step 5: Commit**

```bash
git add config_gui_cpu.py my_model_arch/cpu_fast/pipeline.py \
tests/test_config_gui_camera.py tests/test_pipeline_runtime.py \
docs/ubuntu-xorg-port-progress.md
git commit -m "fix: hand off Ubuntu calibration window"
```
