# Linux Calibration Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run Ubuntu calibration in a dedicated Python process so OpenCV Qt5 HighGUI never shares a process with the PySide6/Qt6 configuration GUI.

**Architecture:** A small `calibration_worker` module owns Linux calibration, Gemini 335, X11 desktop lifetime, HighGUI, cleanup, and one strict JSON result line. `ConfigWindow` uses a single `QProcess` to start that worker, forward output, validate the result, restore the GUI, and preserve the existing Windows path.

**Tech Stack:** Python 3.11, PySide6 `QProcess`, OpenCV Qt5 HighGUI, PyYAML, pytest, Xorg, Orbbec Gemini 335 RGB

## Global Constraints

- Ubuntu calibration must not call OpenCV HighGUI in the PySide6 process.
- The worker command is `sys.executable -u -m my_model_arch.cpu_fast.calibration_worker --config <absolute-config-path>`.
- Success stdout contains exactly one `NEUGAZE_CALIBRATION_RESULT=` line with exact JSON keys `calibration_time` and `model_path`.
- The accepted model path is exactly `model_weights/<calibration_time>/model.pkl`, relative to and contained by the repository root, and the file must exist.
- Gemini 335 remains RGB 1280×720@30 FPS; no depth or IR.
- Windows retains its current synchronous calibration path.
- Do not add retry, camera-backend fallback, old-model fallback, result inference from directory timestamps, worker manager/factory abstractions, or swallowed errors.
- Worker tracebacks and cleanup failures remain observable; the parent restores its window before reporting a child failure.
- Evaluation, expression recognition, robot terminal actions, wheel behavior, and SONIC planning are out of scope.
- The existing untracked `Log/` belongs to the user’s latest hardware run and must not be edited, deleted, or committed.

---

### Task 1: Strict calibration worker and result protocol

**Files:**
- Create: `my_model_arch/cpu_fast/calibration_worker.py`
- Create: `tests/test_calibration_worker.py`

**Interfaces:**
- Produces: `RESULT_PREFIX: bytes`
- Produces: `parse_calibration_result(stdout: bytes, repository_root: Path) -> tuple[str, str]`
- Produces: `run_calibration(config_path: Path, output: BinaryIO, repository_root: Path) -> tuple[str, str]`
- Produces: module CLI `python -m my_model_arch.cpu_fast.calibration_worker --config PATH`

- [ ] **Step 1: Write failing protocol tests**

Create tests for one valid result and every invalid boundary:

```python
def write_model(root, calibration_time="20260727_120000"):
    path = root / "model_weights" / calibration_time / "model.pkl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"model")
    return path


def test_parse_calibration_result_accepts_one_exact_existing_model(tmp_path):
    model = write_model(tmp_path)
    stdout = (
        b"training log\n"
        b'NEUGAZE_CALIBRATION_RESULT={"calibration_time":'
        b'"20260727_120000","model_path":'
        b'"model_weights/20260727_120000/model.pkl"}\n'
    )

    assert parse_calibration_result(stdout, tmp_path) == (
        "20260727_120000",
        model.relative_to(tmp_path).as_posix(),
    )
```

Parameterize missing marker, two markers, invalid UTF-8 payload, invalid JSON,
missing/extra keys, non-string values, invalid timestamp, mismatched timestamp,
absolute path, `..` escape, wrong filename, and missing file. Every case must
raise its original JSON/Unicode error or a specific `RuntimeError`,
`ValueError`, or `FileNotFoundError`; none may return `None`.

- [ ] **Step 2: Run protocol tests and verify RED**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_calibration_worker.py -v
```

Expected: collection fails because `calibration_worker` does not exist.

- [ ] **Step 3: Implement the strict parser**

Implement direct parsing:

```python
RESULT_PREFIX = b"NEUGAZE_CALIBRATION_RESULT="
CALIBRATION_TIME = re.compile(r"\A\d{8}_\d{6}\Z")


def parse_calibration_result(stdout, repository_root):
    result_lines = [
        line for line in stdout.splitlines()
        if line.startswith(RESULT_PREFIX)
    ]
    if len(result_lines) != 1:
        raise RuntimeError(
            "calibration worker stdout must contain exactly one "
            f"{RESULT_PREFIX.decode('ascii')} line; got {len(result_lines)}"
        )
    payload = json.loads(
        result_lines[0][len(RESULT_PREFIX):].decode("utf-8")
    )
    if not isinstance(payload, dict) or set(payload) != {
        "calibration_time", "model_path"
    }:
        raise ValueError("calibration result must contain exactly ...")
    calibration_time = payload["calibration_time"]
    model_path = payload["model_path"]
    if not isinstance(calibration_time, str) or not isinstance(model_path, str):
        raise TypeError("calibration result values must be strings")
    if CALIBRATION_TIME.fullmatch(calibration_time) is None:
        raise ValueError("invalid calibration_time ...")
    expected = PurePosixPath(
        f"model_weights/{calibration_time}/model.pkl"
    )
    if PurePosixPath(model_path) != expected:
        raise ValueError(f"model_path must equal {expected.as_posix()!r}")
    root = repository_root.resolve()
    resolved = (root / Path(model_path)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("model_path escapes repository root")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return calibration_time, expected.as_posix()
```

Use full field names in actual error messages.

- [ ] **Step 4: Write failing worker lifecycle tests**

Build a minimal valid YAML mapping from `configs/cpu.yaml`. Monkeypatch
`RealAction` and `desktop` with event-recording fakes. Cover:

```python
def test_run_calibration_cleans_pipeline_and_desktop_before_result(
    tmp_path, monkeypatch
):
    events = []
    class RecordingOutput(io.BytesIO):
        def write(self, data):
            events.append("result.write")
            return super().write(data)

    output = RecordingOutput()
    model = write_model(tmp_path)
    pipeline = FakePipeline(events, calibration_time="20260727_120000")
    monkeypatch.setattr(worker, "RealAction", lambda **kwargs: pipeline)
    monkeypatch.setattr(
        worker.desktop, "initialize", lambda: events.append("desktop.init")
    )
    monkeypatch.setattr(
        worker.desktop, "close", lambda: events.append("desktop.close")
    )

    result = worker.run_calibration(
        config_path, output, repository_root=tmp_path
    )

    assert result == ("20260727_120000", model.relative_to(tmp_path).as_posix())
    assert events == [
        "desktop.init",
        "pipeline.start",
        "pipeline.quit",
        "desktop.close",
        "result.write",
    ]
```

Also cover pipeline construction failure, calibration failure, pipeline cleanup
failure, desktop cleanup failure, cancellation (`start_calibration()` returns
`None`), missing `calibration_time`, missing model, and output write failure.
For a primary error plus cleanup error, assert the primary object identity and
its added notes.

- [ ] **Step 5: Implement worker construction, cleanup, and CLI**

The worker must import `RealAction` normally but never import PySide6. Load YAML,
require a mapping, construct `RealAction` with the same exact configuration
arguments as `ConfigWindow.initialize_pipeline()`, then:

```python
def run_calibration(config_path, output, repository_root=REPOSITORY_ROOT):
    pipeline = None
    pipeline_cleanup_attempted = False
    desktop_cleanup_attempted = False
    desktop.initialize()
    try:
        config = load_config(config_path)
        pipeline = build_pipeline(config)
        completed = pipeline.start_calibration()
        if completed is not True:
            raise RuntimeError("calibration did not complete")
        calibration_time = pipeline.calibration_time
        model_path = (
            f"model_weights/{calibration_time}/model.pkl"
        )
        parse_calibration_result(
            RESULT_PREFIX + json.dumps({
                "calibration_time": calibration_time,
                "model_path": model_path,
            }, separators=(",", ":")).encode("utf-8"),
            repository_root,
        )
        if not pipeline.quit:
            pipeline_cleanup_attempted = True
            pipeline.quit_pipeline()
        desktop_cleanup_attempted = True
        desktop.close()
    except BaseException as error:
        if (
            pipeline is not None
            and not pipeline.quit
            and not pipeline_cleanup_attempted
        ):
            try:
                pipeline_cleanup_attempted = True
                pipeline.quit_pipeline()
            except BaseException as cleanup_error:
                error.add_note(f"pipeline cleanup also failed: {cleanup_error!r}")
        if not desktop_cleanup_attempted:
            try:
                desktop_cleanup_attempted = True
                desktop.close()
            except BaseException as cleanup_error:
                error.add_note(f"desktop cleanup also failed: {cleanup_error!r}")
        raise

    result_line = RESULT_PREFIX + json.dumps(...).encode("utf-8") + b"\n"
    output.write(result_line)
    output.flush()
    return calibration_time, model_path
```

Do not literally duplicate JSON construction: create the payload once, validate
it, clean resources, then write that same payload. Ensure each cleanup operation
is attempted at most once, including when that cleanup itself raises. `main()`
passes `sys.stdout.buffer`, uses `argparse`, changes no environment variables,
and lets uncaught errors produce the normal Python traceback and nonzero exit.

- [ ] **Step 6: Run Task 1 tests and commit**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_calibration_worker.py -v
/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile \
my_model_arch/cpu_fast/calibration_worker.py
git add my_model_arch/cpu_fast/calibration_worker.py \
tests/test_calibration_worker.py
git commit -m "feat: add isolated Linux calibration worker"
```

Expected: all Task 1 tests pass and compile exits 0.

### Task 2: Linux GUI QProcess success path

**Files:**
- Modify: `config_gui_cpu.py:15-30,348-360,1505-1615`
- Modify: `tests/test_config_gui_camera.py`

**Interfaces:**
- Consumes: Task 1 `parse_calibration_result`
- Produces: `ConfigWindow.calibration_process: QProcess | None`
- Produces: `ConfigWindow._start_linux_calibration() -> None`
- Produces: `ConfigWindow._read_calibration_stdout() -> None`
- Produces: `ConfigWindow._read_calibration_stderr() -> None`
- Produces: `ConfigWindow._finish_linux_calibration(exit_code, exit_status) -> None`

- [ ] **Step 1: Write failing Linux process-routing tests**

Add a `FakeSignal` and `FakeProcess` implementing the used `QProcess` surface.
Test that Linux:

- closes preview before constructing the process;
- never calls `initialize_pipeline` or a local pipeline;
- sets program to `sys.executable`;
- sets exact arguments `-u -m my_model_arch.cpu_fast.calibration_worker
  --config <resolved-current-config>`;
- sets working directory to the repository root;
- connects stdout, stderr, and finished exactly once;
- starts successfully, disables change/calibrate/evaluate, then hides the GUI;
- returns `None` immediately while the child remains running.

Keep and rerun the existing Windows test, which must still return the local
pipeline result without constructing a `QProcess`.

- [ ] **Step 2: Run routing tests and verify RED**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_config_gui_camera.py \
-k 'calibration and (process or windows)' -v
```

Expected: Linux assertions fail because it still calls the local pipeline.

- [ ] **Step 3: Implement Linux QProcess startup**

Import `QProcess` and `parse_calibration_result`. Initialize:

```python
self.calibration_process = None
self.calibration_stdout = bytearray()
self.calibration_stderr = bytearray()
```

In `start_calibration`, keep preview close/error handling, then branch:

```python
if self.camera_platform == "linux":
    return self._start_linux_calibration()
```

`_start_linux_calibration` rejects a non-`None` process, requires an existing
`current_config_path`, builds one child `QProcess(self)`, connects its three
signals, sets the exact program/arguments/cwd, and calls `start()`. It calls
`waitForStarted(5000)` exactly once. Failure uses `errorString()` in a
`RuntimeError`, clears the process, restores enabled camera-change state,
shows a full traceback, and re-raises. Success disables the three camera
buttons and hides the main window.

- [ ] **Step 4: Write failing output and success-completion tests**

Test stdout/stderr readers with byte chunks. They must append exact bytes and
write/flush the same bytes to `sys.stdout.buffer` and `sys.stderr.buffer`.

For completion, create a real model file under the monkeypatched repository
root, emit stdout containing normal logs plus one result line, and call the
finished handler with `QProcess.NormalExit` and exit code 0. Assert:

- main window is shown before parsing/result application;
- process reference and byte buffers are cleared only after local copies exist;
- `regression_model_path` receives the exact relative path;
- configuration save and existing “restart preview?” question run once;
- camera buttons return to enabled state;
- `deleteLater()` runs exactly once.

- [ ] **Step 5: Implement success completion without duplication**

Extract the existing successful UI work into:

```python
def _apply_calibration_model(self, model_path):
    self.preview_label.setText(...)
    self.integrated_widgets["regression_model_path"].setText(model_path)
    self.save_config()
    reply = QMessageBox.question(...)
    if reply == QMessageBox.Yes:
        self.restart_camera_preview()
```

`on_calibration_finished()` derives the Windows model path and calls this
method, preserving Windows behavior. Linux `_finish_linux_calibration` restores
the window, copies outputs, clears process ownership, checks normal/zero exit,
calls `parse_calibration_result`, then calls `_apply_calibration_model`.

- [ ] **Step 6: Run Task 2 tests and commit**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_config_gui_camera.py tests/test_calibration_worker.py -v
git add config_gui_cpu.py tests/test_config_gui_camera.py
git commit -m "feat: run Linux calibration in worker process"
```

Expected: all selected tests pass.

### Task 3: Child failure, reentry, and GUI close boundaries

**Files:**
- Modify: `config_gui_cpu.py:1505-1640`
- Modify: `tests/test_config_gui_camera.py`

**Interfaces:**
- Consumes: Task 2 QProcess state and completion methods.
- Produces: one visible error path for failed start and failed completion.
- Produces: close-event refusal while a calibration worker is running.

- [ ] **Step 1: Write failing failure-protocol tests**

Parameterize:

- `FailedToStart` / `waitForStarted(False)` with exact `errorString`;
- nonzero normal exit with captured stderr traceback;
- crashed exit with code and captured stderr;
- missing, duplicate, invalid JSON, invalid schema, escaping path, mismatched
  path, and missing model result;
- result parser success followed by `save_config` or preview-restart failure.

Every case must restore/show the main window before `QMessageBox.critical`,
disable calibration/evaluation after failure, keep camera change available,
delete the finished process once, and re-raise the same local parser/UI error
object when the handler is invoked directly. Child failures must include the
full decoded stderr and exit status; they may not reuse an old model.

- [ ] **Step 2: Write failing reentry and close tests**

```python
def test_linux_calibration_rejects_second_running_process(...):
    window.calibration_process = running_process
    with pytest.raises(RuntimeError, match="already running"):
        window.start_calibration()
    assert no_new_process_was_created


def test_close_event_is_rejected_while_calibration_process_runs(...):
    event = FakeCloseEvent()
    window.calibration_process = running_process
    window.closeEvent(event)
    assert event.ignored is True
    assert window.is_shown is True
    assert warning_mentions_esc_q
    assert running_process.terminate_calls == 0
    assert running_process.kill_calls == 0
```

Also verify `check_hotkeys` does not attempt parent pipeline cleanup when the
Linux child owns calibration.

- [ ] **Step 3: Implement one explicit failure handler**

Use a direct helper:

```python
def _show_linux_calibration_error(self, formatted_traceback):
    self.show()
    self.camera_change_btn.setEnabled(True)
    self._disable_camera_actions()
    QMessageBox.critical(
        self, "Calibration Error", formatted_traceback
    )
```

Call it inside a narrow `except` and then use bare `raise`, so parser/UI error
identity and traceback remain intact. A constructed child-process
`RuntimeError` may be passed with its explicit formatted traceback. Completion
must include captured child stderr and exit status in that error.

In `closeEvent`, if `calibration_process.state() != QProcess.NotRunning`, call
`event.ignore()`, show the main window, and display a warning instructing
ESC+Q. Return without closing camera/desktop and without terminating the child.

- [ ] **Step 4: Run Task 3 tests and commit**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_config_gui_camera.py tests/test_calibration_worker.py -v
/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile \
config_gui_cpu.py my_model_arch/cpu_fast/calibration_worker.py
git add config_gui_cpu.py tests/test_config_gui_camera.py
git commit -m "fix: expose calibration worker failures"
```

Expected: all selected tests pass and compile exits 0.

### Task 4: Qt5/Qt6 process-isolation verification and Chinese progress

**Files:**
- Create: `tests/test_calibration_process_isolation.py`
- Modify: `docs/ubuntu-xorg-port-progress.md`
- Modify: `docs/ubuntu-xorg-manual-test.md`

**Interfaces:**
- Verifies: a PySide6 parent can synchronously wait for a child OpenCV Qt5
  window probe without deadlocking in `cv2.namedWindow`.
- Records: root cause, worker architecture, automated evidence, and remaining
  Gemini 335 manual calibration.

- [ ] **Step 1: Write the Xvfb process-isolation regression**

Mark the test `x11`. In the PySide6 test process, create a `QApplication`, then
start a child using `QProcess` and the current interpreter with `-c` code that:

```python
import cv2
import numpy as np

cv2.namedWindow("calibration-worker-probe", cv2.WINDOW_NORMAL)
cv2.imshow(
    "calibration-worker-probe",
    np.full((48, 64, 3), 225, dtype=np.uint8),
)
cv2.waitKey(20)
cv2.destroyAllWindows()
print("CALIBRATION_WORKER_WINDOW_OK", flush=True)
```

Require `waitForStarted(5000)` and `waitForFinished(5000)`, normal exit 0,
the exact stdout marker, and empty stderr. Do not run this probe in the parent.

- [ ] **Step 2: Run the isolation test**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_calibration_process_isolation.py -m x11 -v
```

Expected: PASS without hanging in `namedWindow`.

- [ ] **Step 3: Update Chinese progress and manual commands**

Record:

- production stack dump at `pipeline.py:1270 cv2.namedWindow`;
- OpenCV GUI backend `QT5 5.15.16`, PySide6 Qt6 parent, and no Xorg `track`;
- standalone HighGUI success and same-process failure;
- the exact worker command and strict result protocol;
- automated worker/GUI/isolation test results;
- the user must still execute a full Gemini 335 calibration.

Add manual commands:

```bash
conda activate neugaze
cd /home/yixiao/Users/yixiao/Misc/NeuGaze/.worktrees/ubuntu-xorg-port
python config_gui_cpu.py
```

Acceptance requires visible fullscreen `track`, completed model/config update,
and a separate ESC+Q cancellation run. Do not include Windows instructions.

- [ ] **Step 4: Run full verification**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v
/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile \
config_gui_cpu.py my_model_arch/cpu_fast/calibration_worker.py
git diff --check
```

Expected: all selected tests pass; only the compositor-dependent positive
overlay test may skip, and the explicit Gemini hardware test remains
deselected without `--run-orbbec`.

- [ ] **Step 5: Commit**

```bash
git add tests/test_calibration_process_isolation.py \
docs/ubuntu-xorg-port-progress.md docs/ubuntu-xorg-manual-test.md
git commit -m "docs: record isolated calibration verification"
```

- [ ] **Step 6: Run Gemini 335 boundary smoke without claiming acceptance**

Run the install/runtime diagnostics and the existing explicit 100-frame Gemini
test only if the camera is still connected:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
/home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest \
tests/test_orbbec_hardware.py --run-orbbec -v
```

Record this separately from the user-driven full calibration. Passing the
100-frame test proves camera ownership and RGB reads, not gaze calibration UI,
model training, or human acceptance.
