# 🎯 NeuGaze: Facial Expression & Gaze-Based Computer Control

<div align="left">

**[中文文档](README-CN.md) | English**

[![arXiv](https://img.shields.io/badge/arXiv-2504.15101-b31b1b.svg)](https://arxiv.org/abs/2504.15101)
[![Demo Video](https://img.shields.io/badge/Demo-Bilibili-00A1D6)](https://www.bilibili.com/video/BV1kKdYYVEEM/#reply270100925344)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Ubuntu-blue.svg)](#-requirements)
[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

*A non-invasive computer control system that combines facial expression recognition, head movement tracking, and gaze estimation, designed for hands-free human-computer interaction.*

The current Ubuntu 24.04 Xorg path combines facial actions with head-direction selection and prints robot action labels for the planned GR00T Whole-Body Control and SONIC reference-motion integration. Ubuntu does not emit game keys.


## 📋 Table of Contents

- [🎯 Overview](#-overview)
- [📊 Performance Evaluation](#-performance-evaluation)
- [🚀 Installation](#-installation)
- [🎮 Quick Start](#-quick-start)
- [😊 Expression & Control Configuration](#-expression--control-configuration)
- [🎯 Use Cases](#-use-cases)
- [⚙️ Technical Details](#️-technical-details)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

---

## 🎯 Overview

Traditional assistive technologies face significant limitations: invasive brain-computer interfaces like Neuralink require surgical implantation, commercial eye trackers like Tobii lack precision for complex operations, and traditional assistive devices often involve cumbersome controls. **NeuGaze** addresses these challenges by integrating facial expressions, head movements, and gaze estimation to create an intuitive, hands-free control system.

### 🖥️ Requirements

| Component | Requirement | Description |
|-----------|-------------|-------------|
| 📷 **Camera** | Orbbec Gemini 335 or webcam | Orbbec SDK RGB or OpenCV/V4L2 |
| 💻 **Processor** | CPU-only operation | No GPU required |
| 🪟 **OS** | Windows or Ubuntu 24.04 Xorg | Wayland is not supported |

### ⭐ Key Features

<div align="left">

| Feature | Description | Icon |
|---------|-------------|------|
| **Head-pose four-way selection** | Open the full-screen selector and choose robot actions by head direction | 🎯 |
| **Facial expression mapping** | Validated robot action labels | 😊 |
| **Multi-modal control** | Combining head direction with facial actions | 🤖 |
| **Customizable configurations** | Adaptable for different use cases | ⚙️ |
| **Real-time performance** | CPU-optimized inference | 🚀 |

</div>

---

## 📊 Performance Evaluation

We conducted comprehensive testing using progressive training on multiple calibration datasets. The system achieves stable gaze tracking performance with the following metrics:

### 📈 Performance Metrics

- **Mean Error**: **48mm** (original)
- **After Kalman Filtering**: **40mm** (optimized)
- **Display Resolution**: 3072×1920
- **Training Data**: Multiple calibration datasets

> 💡 **Note**: Current performance is indeed inferior to Tobii's results, but we welcome community collaboration for improvements!

![Progressive Training Analysis](results/progressive_training/comprehensive_comparison.png)

*Progressive training results showing error reduction and performance stability across multiple datasets. The analysis demonstrates consistent improvement in gaze accuracy as more training data is incorporated.*

---

## 🚀 Installation

NeuGaze has one shared Python pipeline, plus platform-, camera-, and test-specific components. Install the complete runtime file for your platform; do not assemble a partial environment package by package.

### 🧩 What Each Dependency Group Provides

| Section | Components | Required for |
|---|---|---|
| Core vision and gaze | PyTorch, TorchVision, NumPy, MediaPipe, OpenCV, ONNX Runtime, NCNN | Face detection, expression recognition, gaze estimation, and model inference |
| Calibration and state | scikit-learn, FilterPy, jsonlines, PyYAML | Calibration regression, gaze smoothing, records, and configuration |
| GUI and desktop | PySide6; `python-xlib` on Ubuntu; PyWin32 on Windows | Configuration GUI, overlay, wheel, and platform desktop integration |
| Camera | `pyorbbecsdk2` for Gemini 335; OpenCV/V4L2 for standard Linux video devices | RGB frame acquisition from the explicitly selected backend |
| Robot terminal output | Python standard library only | Printing validated robot action terms on Ubuntu; no SONIC dependency |
| Development tests | pytest; Xvfb/Xauth for isolated X11 tests | Optional automated testing, not normal NeuGaze runtime |

`requirements-ubuntu.txt` is the reproducible full Ubuntu runtime lock. Torchaudio and tqdm are not directly imported by the main GUI path, but they remain pinned until the runtime and model-conversion environments are split and clean-install tested. Today, the safe reduction is to leave test requirements and Xvfb/Xauth uninstalled during normal runtime. Camera/backend and conversion-package splits require a separate clean-install change; do not hand-edit the runtime lock.

### 1. Create the Conda Environment

Use the same Python version on both platforms:

```bash
conda create -n neugaze python=3.11.11
conda activate neugaze
```

### 2. Windows Runtime

`requirements.txt` installs the Windows desktop/game output backend and the shared gaze pipeline. Install it with explicit commands:

```bash
python -m pip install -r requirements.txt
python config_gui_cpu.py
```

### 3. Ubuntu 24.04 Runtime

#### 3.1 Xorg and GUI Components

Select **Ubuntu on Xorg** from the login-screen gear menu. Wayland is not supported. XTest and XFixes are required by the X11 backend. `libxcb-cursor0` supports the Qt GUI; `xcompmgr` is required when the gaze overlay is enabled.

The read-only checker reports missing host components. Install system packages only when it reports them missing:

```bash
export NEUGAZE_ORBBEC_SDK_ROOT=/absolute/path/to/OrbbecSDK_v2
python scripts/check_ubuntu_install.py \
  --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" \
  --require-overlay

sudo apt-get update
sudo apt-get install --no-install-recommends xcompmgr libxcb-cursor0
```

Normal NeuGaze diagnostics and runtime commands do not use `sudo`.

#### 3.2 Python Runtime Components

Install the complete CPU runtime lock, then remove the conflicting OpenCV wheel that two upstream packages install transitively:

```bash
python -m pip install -r requirements-ubuntu.txt
python -m pip uninstall -y opencv-python
python -m pip install --no-deps --force-reinstall \
  opencv-contrib-python==4.11.0.86
```

This installs the core vision, model inference, calibration, GUI, X11, and both camera backends listed above.

#### 3.3 Camera Components

Choose exactly one backend in the GUI; NeuGaze does not silently switch to the other backend after a failure.

- **Orbbec SDK / Gemini 335:** uses `pyorbbecsdk2==2.1.1` and its bundled SDK 2.8.6. `NEUGAZE_ORBBEC_SDK_ROOT` is only the authoritative source for the udev rule installer. A separately installed system SDK 2.9.3 is not required.
- **OpenCV / V4L2:** uses the selected `/dev/videoN` device and does not require the Orbbec udev rule at runtime.

If the checker reports a missing or mismatched Gemini 335 udev rule, install only the rule from the selected SDK source tree, then rerun the checker:

```bash
sudo "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/install_udev_rules.sh"
python scripts/check_ubuntu_install.py \
  --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" \
  --require-overlay
```

#### 3.4 Verify and Launch

The runtime diagnostic verifies Xorg, X11 extensions, the compositor, model assets, the selected camera, and the Orbbec wheel/SDK ABI. It is read-only and fails visibly when a requirement is wrong.

```bash
python scripts/check_ubuntu_runtime.py \
  --config configs/cpu.yaml \
  --require-overlay
python config_gui_cpu.py
```

Do not use `LD_LIBRARY_PATH`, `LD_PRELOAD`, library replacement, or a camera backend fallback to hide a diagnostic failure.

### 4. Optional Development and Hardware Tests

Normal NeuGaze runtime does not require pytest, Xvfb, or Xauth.

```bash
python -m pip install -r requirements-dev.txt
sudo apt-get install --no-install-recommends xvfb xauth
```

With a Gemini 335 connected, the explicit hardware test reads 100 frames, closes the device, reopens it, and reads one more frame:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v
```

### 5. Known OpenCV Metadata Warning

<details>
<summary>Why <code>python -m pip check</code> reports two missing dependencies</summary>

`pyorbbecsdk2==2.1.1` and `ncnn==1.0.20260526` declare the distribution name `opencv-python`, while NeuGaze deliberately installs `opencv-contrib-python==4.11.0.86`. Both wheels own the same `cv2` files and must not be installed together.

Consequently, `python -m pip check` is expected to exit 1 with:

```text
pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.
ncnn 1.0.20260526 requires opencv-python, which is not installed.
```

This is a package-metadata exception, not a missing `cv2` runtime. Do not install an alias/dummy package, edit installed metadata, or restore `opencv-python`. Use the runtime diagnostic and hardware test as the executable checks.

</details>

---

## 🎮 Quick Start

### 📹 Video Tutorial

Watch this video to quickly understand the system usage:

![Quick Start](assets/demo.gif)

### 📋 Step-by-Step Guide

#### 1️⃣ Launch the GUI

```bash
python config_gui_cpu.py
```

#### 2️⃣ Camera Setup

- 📷 Select your camera (default: camera 0)
- 👤 Position your face in the center of the preview window
- ✅ Click "Confirm Selection"

![Camera Selection](assets/camera%20selection.png)

#### 3️⃣ Calibration Process

- 🎯 Click "Start Calibration"
- 👁️ Follow the on-screen dots with your gaze
- 👀 Keep your eyes open (photos are only taken when eyes are detected)
- ⏳ Wait for calibration to complete

#### 4️⃣ Start Control

- Click "Start Evaluation". Recognition runs on a background thread, so configuration tabs remain viewable. Camera switching and recalibration controls are disabled while the camera is in use, and the button changes to "Stop Evaluation"
- After one successful calibration, the GUI stores the generated `model.pkl` path in `regression_model_path`; later launches can go directly to "Start Evaluation" without recalibrating every time
- Open your mouth to show the transparent full-screen four-region selector; keep it open, move your head toward the target direction, then close your mouth to confirm
- Pucker your lips, raise your inner brows, or close only your left eye to trigger direct robot action labels
- Ubuntu prints `[ROBOT_ACTION]` lines and does not emit keyboard or mouse events

Recalibrate when the model file is missing, the user changes, the camera moves substantially, or the screen resolution, scaling, or monitor layout changes. Model-loading errors remain visible; NeuGaze does not silently use an uncalibrated model.

---

## 😊 Expression & Control Configuration

NeuGaze recognizes expressions through `expression_evaluator_config` in
`configs/cpu.yaml`, then maps them to robot action labels through
`robot_action_config`. Ubuntu currently prints labels to validate recognition and
wheel selection; it does not call SONIC or WBC yet.

### 🎭 Expression Detection

MediaPipe blendshapes provide the facial signals. This table is the complete current
Ubuntu robot-output contract:

#### Core Expression Mapping

| User action | MediaPipe condition | Internal expression ID | Current Ubuntu behavior |
|-------------|---------------------|------------------------|-------------------------|
| **Open mouth** | `jawOpen > 0.4`, with no substantial left/right jaw shift | `numlock` | Open the transparent full-screen four-region selector; hold, select by head direction, and close to confirm |
| **Pucker lips** | `mouthPucker > 0.97` and `mouthFunnel < 0.2` | `left_click` | Emit `wave` / **挥手** |
| **Raise inner brows** | `browInnerUp > 0.8` | `num8` | Emit `dance` / **舞蹈** |
| **Close only the left eye** | `eyeBlinkLeft > 0.6` and `eyeBlinkRight < 0.25` | `extra` | Emit `stop` / **停止** |

`left_click`, `num8`, `extra`, and `numlock` are retained internal expression IDs;
they do not mean that Ubuntu clicks a mouse or sends those keyboard keys. Jaw shifts and
left/right or bilateral smiles remain detectable but have no direct robot action binding.
Head pitch and yaw are reserved for four-way selection while the mouth is open.

#### Expression Threshold Adjustment

```cmd
python learn\mediapipe_example.py
```

You can use this program to view the scores for different expressions and adjust the thresholds accordingly.

#### Expression Configuration Example

```yaml
left_click:
  conditions:
  - feature: mouthPucker
    operator: '>'
    threshold: 0.97
  - feature: mouthFunnel
    operator: <
    threshold: 0.2
  combine: AND
```

### 🤖 Ubuntu Robot Action Output

Ubuntu has one `robot_terminal` output path. It does not use the `game`, `game_cs`,
`game_wz`, or `type` key tables and does not emit desktop keyboard/mouse events.

#### Direct expression actions

A direct expression emits once on its rising edge. Holding the expression does not
repeat the output.

| Internal expression ID | Action ID | Terminal label | Source |
|------------------------|-----------|----------------|--------|
| `left_click` | `wave` | **挥手** | `expression` |
| `num8` | `dance` | **舞蹈** | `expression` |
| `extra` | `stop` | **停止** | `expression` |

#### Open-mouth plus full-screen head-direction regions

| Head direction | Action ID | Terminal label |
|----------------|-----------|----------------|
| **Up** | `move_forward_step` | **前进一步** |
| **Down** | `move_backward_step` | **后退一步** |
| **Turn left** | `turn_left` | **左转** |
| **Turn right** | `turn_right` | **右转** |

Usage sequence:

1. Open your mouth to trigger `numlock` and show a transparent selector over the entire primary screen.
2. Keep your mouth open and move your head up, down, left, or right from neutral. The corresponding region highlights after pitch exceeds `10°` or yaw exceeds `12°`. If both axes exceed their thresholds, the larger threshold-normalized movement wins.
3. Hold the target direction and close your mouth to confirm; exactly one selected action label is emitted.
4. Returning to the neutral dead zone clears the selection. Closing there emits an explicit cancellation line and no action.

The selector has a fully transparent background and does not obscure the desktop. It draws only subtle separators, a low-opacity blue highlight for the active head direction, and clean `Noto Sans CJK SC` labels on compact dark rounded panels. The window stays on top, passes clicks through, and never takes focus. The full-screen regions are visual direction feedback; gaze coordinates no longer select an action.

#### Terminal output format

```text
[ROBOT_ACTION] id=wave label=挥手 source=expression
[ROBOT_ACTION] id=dance label=舞蹈 source=expression
[ROBOT_ACTION] id=stop label=停止 source=expression
[ROBOT_ACTION] id=move_forward_step label=前进一步 source=wheel
[ROBOT_ACTION] id=move_backward_step label=后退一步 source=wheel
[ROBOT_ACTION] id=turn_left label=左转 source=wheel
[ROBOT_ACTION] id=turn_right label=右转 source=wheel
```

No wheel selection produces:

```text
[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel
```

These labels are stable action identifiers for the planned GR00T Whole-Body Control /
SONIC reference-motion integration. The current version only prints them.

### ⚙️ Advanced Configuration

Action IDs, Chinese labels, and expression bindings have one source of truth:
`robot_action_config` in `configs/cpu.yaml`. Unknown or missing actions and invalid wheel
configuration fail during startup.

```yaml
robot_wheel_config:
  layout: fullscreen_cardinal
  selection: head_pose
  yaw_threshold_degrees: 12.0
  pitch_threshold_degrees: 10.0
robot_action_config:
  actions:
    move_forward_step: 前进一步
    move_backward_step: 后退一步
    turn_left: 左转
    turn_right: 右转
    wave: 挥手
    dance: 舞蹈
    stop: 停止
```

The robot selector is a fixed transparent full-screen four-way layout and only accepts
`selection: head_pose`. The configuration no longer accepts `radius`; missing, unknown, or
invalid layout, selection, or threshold fields fail during startup.
`yaw_threshold_degrees` and `pitch_threshold_degrees` are offsets from
`head_angles_center` and must be in `(0, 45]`. Head movement does not map to W/S, A/D, or scrolling.

---

## 🎯 Use Cases

### ♿ Accessibility

- **🦽 Mobility Assistance**: Hands-free computer operation for users with limited mobility
- **🏥 Rehabilitation**: Motor skill training through controlled head and facial movements

### 🤖 Robot Control

- **Action-label validation**: Check expression recognition and wheel selection in the terminal
- **Reference-motion integration**: Map the seven stable action IDs to GR00T/WBC reference motions

### 🤖 Smart Device Integration

- **🥽 AR/VR Interfaces**: Natural control for head-mounted displays
- **👓 Smart Glasses**: Expression-based navigation without hand gestures

---

## ⚙️ Technical Details

### 🏗️ Architecture

| Component | Function Description | Technical Implementation |
|-----------|---------------------|-------------------------|
| **🎯 Intent Recognition** | Comprehensive analysis of facial expressions, head movements, and gaze patterns | MediaPipe + custom algorithms |
| **🔄 Intent Mapping** | Convert expressions and wheel regions into stable robot action IDs | `robot_action_config` |
| **🎭 Multi-Modal Fusion** | Integration and prioritization of multiple simultaneous intents | Priority rule engine |
| **⚡ Action Output** | Print action ID, Chinese label, and source | `[ROBOT_ACTION]` terminal protocol |
| **🚀 Optimization** | CPU-optimized inference pipeline for real-time performance | CPU-optimized inference |

### ⚠️ Limitations

| Limitation | Impact | Solution |
|------------|--------|----------|
| **🌞 Lighting Sensitivity** | Performance degrades in poor or uneven lighting | Adjust environmental lighting |
| **🎯 Calibration Required** | Individual calibration needed for optimal accuracy | Regular recalibration |
| **📚 Expression Training** | Learning curve for natural expression control | Practice and adaptation |

---

## 🤝 Contributing

We welcome contributions! Please feel free to submit issues, feature requests, or pull requests.

### 🎯 Contribution Methods

- 🐛 **Report Issues**: Submit bug reports
- 💡 **Feature Suggestions**: Propose new feature ideas
- 🔧 **Code Contributions**: Submit pull requests
- 📚 **Documentation Improvements**: Help improve documentation

---

## 📄 License

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

This project is licensed under Creative Commons Attribution-NonCommercial 4.0 International License.

### ✅ You are free to:

- ✅ Share and adapt the code for personal use
- ✅ Use for research and educational purposes
- ✅ Create derivative works for non-commercial purposes (e.g., streaming, content creation)

### ❌ You may NOT:

- ❌ Sell the source code or derivatives
- ❌ Deploy as commercial hardware/software products
- ❌ Package as paid executable applications
- ❌ Use for commercial web services

> 💡 **Note**: We provide this software freely to benefit the community while preventing exploitation by commercial entities. License terms may be updated to Apache-2.0 or MIT based on community feedback.

---

## 📚 Citation

```bibtex
@article{yang2024neugaze,
  title={NeuGaze: Facial Expression and Gaze-Based Computer Control},
  author={Yang, Yiqian},
  journal={arXiv preprint arXiv:2504.15101},
  year={2024}
}
```

---

<div align="left">

**⚠️ Note**: This system is designed for research and accessibility purposes. While functional, it may require individual tuning for optimal performance. We encourage experimentation and welcome feedback to improve the system's robustness and usability.

---

⭐ **If this project helps you, please give us a star!** ⭐

</div>
