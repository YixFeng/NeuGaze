# Task 1 Report: Test Harness and Explicit Camera Configuration

## Status

Completed and committed after test-first validation.

## Implementation

- Added strict pytest discovery, options, and `x11` / `hardware` markers in `pytest.ini`.
- Added the pinned development test dependency in `requirements-dev.txt`.
- Added immutable `CameraConfig`, explicit backend resolution, and strict stream-value validation in `my_model_arch/cpu_fast/camera.py`.
- Added Linux Orbbec and Win32 OpenCV backend settings, plus the required `1280x720 @ 30 FPS` stream values, to `configs/cpu.yaml`.
- Added camera configuration tests and updated the Ubuntu Xorg progress record.

## Files

- `pytest.ini`
- `requirements-dev.txt`
- `my_model_arch/cpu_fast/camera.py`
- `tests/test_camera_config.py`
- `configs/cpu.yaml`
- `docs/ubuntu-xorg-port-progress.md`

## RED Evidence

Command:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v
```

Result: expected collection failure, `ModuleNotFoundError: No module named 'my_model_arch.cpu_fast.camera'` (0 collected, 1 error).

## GREEN and Focused Regression Evidence

Commands:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v
```

Results: both commands passed all 10 camera-config tests in 0.01s.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is required because system ROS pytest-plugin autoload is contaminated. No dependency was installed, hidden, or replaced.

## Self-review

- Backend selection requires an explicit per-platform mapping; no `auto` or fallback path exists.
- Win32 remains constrained to OpenCV.
- Device ID must be non-negative; dimensions and FPS must be positive.
- Changes do not touch `learn/`, add no root runtime requirement, and preserve Windows camera configuration.
