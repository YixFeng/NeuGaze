# 🎯 NeuGaze: Facial Expression & Gaze-Based Computer Control

<div align="left">

**[中文文档](README-CN.md) | English**

[![arXiv](https://img.shields.io/badge/arXiv-2504.15101-b31b1b.svg)](https://arxiv.org/abs/2504.15101)
[![Demo Video](https://img.shields.io/badge/Demo-Bilibili-00A1D6)](https://www.bilibili.com/video/BV1kKdYYVEEM/#reply270100925344)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Ubuntu-blue.svg)](#-requirements)
[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

*A non-invasive computer control system that combines facial expression recognition, head movement tracking, and gaze estimation, designed for hands-free human-computer interaction.*

This system enables complex action game control, as demonstrated in the video showing Black Myth: Wukong defeating the Yin Tiger boss. It can also be used to play MOBA games like Honor of Kings, FPS games like CS2, and many other game types.


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
| **Gaze-based mouse control** | Real-time calibration, precise tracking | 🎯 |
| **Facial expression mapping** | Keyboard/mouse action mapping | 😊 |
| **Three-modal control** | Combining gaze, expressions, and head movements | 🎮 |
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

- 🎮 Click "Start Evaluation"
- 🖱️ Your mouse cursor will now follow your gaze
- 😊 Use facial expressions to trigger actions

---

## 😊 Expression & Control Configuration

NeuGaze uses a sophisticated expression recognition system defined in `configs/cpu.yaml`. The system supports multiple control modes and customizable mappings.

### 🎭 Expression Detection

The system recognizes facial expressions through MediaPipe landmarks and maps them to specific actions:

#### Core Expression Mapping

| Expression | Action Description | Triggered Operation |
|------------|-------------------|---------------------|
| **Open Mouth** (`jawOpen`) | *Drop your jaw naturally* | 🎯 Mode selector - displays available control wheels |
| **Pucker Lips** (`mouthPucker`) | *Make a kissing motion with pursed lips* | 🖱️ Left mouse click |
| **Jaw Left** (`jawLeft`) | *Shift your jaw to the left side* | 🖱️ Right mouse click |
| **Jaw Right** (`jawRight`) | *Shift your jaw to the right side* | 🖱️ Middle mouse click |
| **Smile Left** (`mouthSmileLeft`) | *Smile with only the left side of your mouth* | 🧭 Navigation/selection |
| **Smile Right** (`mouthSmileRight`) | *Smile with only the right side of your mouth* | 🧭 Navigation/selection |
| **Both Sides Smile** | *Full natural smile with both sides* | ⚡ Special commands |
| **Head Movements** | *Tilt, turn, and nod your head* | ⌨️ WASD keys and scrolling |

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

### 🎮 Control Modes

The system supports multiple operation modes through the wheel interface:

#### 🎯 1. Game Mode (`game`)

Optimized for gaming with WASD movement and common game keys:

| Wheel Position | Key Mapping | Function Description |
|----------------|-------------|---------------------|
| **num1** | Z/X/C keys | 🎮 Common game actions |
| **num2** | Shift | 🏃 Sprint/crouch |
| **num4** | Number keys 1-4 | ⚔️ Weapon selection |
| **num6** | Q/R/F/T keys | 🎯 Interaction keys |
| **num8** | Space | ⚡ Jump |

#### 🎯 2. CS:GO Mode (`game_cs`)

Specialized for Counter-Strike with tactical bindings:

| Wheel Position | Key Mapping | Function Description |
|----------------|-------------|---------------------|
| **num2** | Space | ⬆️ Jump |
| **num8** | Shift | 🚶 Walk/precision |
| **Mouse lock** | Disabled | 🎯 For precise aiming |

#### 🎯 3. Honor of Kings Mode (`game_wz`)

Optimized for MOBA gameplay (王者荣耀/Arena of Valor):

| Wheel Position | Key Mapping | Function Description |
|----------------|-------------|---------------------|
| **num1-3** | Skill activation | ⚔️ Skills 1-3 |
| **num4** | M key | 🗺️ Map |

#### ⌨️ 4. Typing Mode (`type`)

Full keyboard access for text input:

| Wheel Position | Key Mapping | Function Description |
|----------------|-------------|---------------------|
| **num4** | Complete alphabet | 🔤 Square layout letters |
| **num6** | Numbers and symbols | 🔢 Square layout numbers and symbols |
| **num2** | Modifier keys | ⌨️ Shift, Ctrl, Alt, etc. |
| **num3** | Common shortcuts | 📋 Ctrl+C, Ctrl+V, etc. |

### ⚙️ Advanced Configuration

#### 🎯 Expression Priorities

The system includes priority rules to prevent conflicting expressions:

```yaml
priority_rules:
- when: num7
  disable: [num2]
  except: []
```

#### 🎨 Wheel Layouts

Different input modes support different wheel layouts:

| Layout Type | Description | Use Case |
|-------------|-------------|----------|
| **Default** | Circular arrangement | 🎮 Gaming modes |
| **Square** | Grid layout | ⌨️ Letter and symbol input |

#### 🎯 Head Movement Integration

Head orientation controls additional functions:

| Head Movement | Key Mapping | Function Description |
|---------------|-------------|---------------------|
| **Pitch (up/down)** | W/S keys | ⬆️⬇️ Up/down movement |
| **Yaw (left/right)** | A/D keys | ⬅️➡️ Left/right movement |
| **Roll (tilt)** | Scroll wheel | 🔄 Scrolling operations |

---

## 🎯 Use Cases

### ♿ Accessibility

- **🦽 Mobility Assistance**: Hands-free computer operation for users with limited mobility
- **🏥 Rehabilitation**: Motor skill training through controlled head and facial movements

### 🎮 Gaming & Entertainment

- **🎯 Immersive Gaming**: Novel input method for enhanced gaming experiences
- **🐒 Action Games**: Complex action game control as demonstrated with Black Myth: Wukong boss battles
- **🏆 MOBA Games**: Strategic gameplay in Honor of Kings and similar MOBAs
- **🎯 FPS Games**: Precision control for Counter-Strike 2 and other competitive shooters
- **💪 Muscle Training**: Facial and neck muscle exercise through interactive control

### 🤖 Smart Device Integration

- **🥽 AR/VR Interfaces**: Natural control for head-mounted displays
- **👓 Smart Glasses**: Expression-based navigation without hand gestures

---

## ⚙️ Technical Details

### 🏗️ Architecture

| Component | Function Description | Technical Implementation |
|-----------|---------------------|-------------------------|
| **🎯 Intent Recognition** | Comprehensive analysis of facial expressions, head movements, and gaze patterns | MediaPipe + custom algorithms |
| **🔄 Intent Mapping** | Translation of recognized intents into specific keyboard/mouse actions | Configuration-driven mapping system |
| **🎭 Multi-Modal Fusion** | Integration and prioritization of multiple simultaneous intents | Priority rule engine |
| **⚡ Action Execution** | Coordinated control system enabling complex gaming operations | Real-time control interface |
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
