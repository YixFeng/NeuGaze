# 🎯 NeuGaze: 基于头部动作、面部表情与凝视的计算机控制系统

<div align="left">

**中文文档 | [English](README.md)**

[![arXiv](https://img.shields.io/badge/arXiv-2504.15101-b31b1b.svg)](https://arxiv.org/abs/2504.15101)
[![演示视频](https://img.shields.io/badge/Demo-Bilibili-00A1D6)](https://www.bilibili.com/video/BV1kKdYYVEEM/#reply270100925344)
[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Ubuntu-blue.svg)](#-硬件要求)
[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
QQ 群 ：809133143
*一个结合面部表情识别、头部动作追踪和凝视估计的非侵入式计算机控制系统，专为免手操作的人机交互而设计。*

当前 Ubuntu 24.04 Xorg 版本使用面部动作与头部方向选择输出机器人动作词条，可选择在 Terminal 验证，或通过本机 ZeroMQ IPC 驱动 SONIC 中预加载的 reference motion；Ubuntu 不发送游戏键位。



---

## 📋 目录

- [🎯 项目概述](#-项目概述)
- [📊 性能评估](#-性能评估)
- [🚀 快速安装](#-快速安装)
- [🎮 快速开始](#-快速开始)
- [😊 表情与控制配置](#-表情与控制配置)
- [🎯 使用场景](#-使用场景)
- [⚙️ 技术细节](#️-技术细节)
- [🤝 贡献](#-贡献)
- [📄 许可证](#-许可证)

---

## 🎯 项目概述

传统辅助技术存在显著局限：像Neuralink这样的侵入式脑机接口需要手术植入，Tobii等商业眼动仪缺乏复杂操作的精度，传统辅助设备往往涉及繁琐的控制方式。**NeuGaze**通过整合面部表情、头部动作和凝视估计来解决这些挑战，创造出直观的免手控制系统。

### 🖥️ 硬件要求

| 组件 | 要求 | 说明 |
|------|------|------|
| 📷 **摄像头** | Orbbec Gemini 335 或普通摄像头 | Orbbec SDK RGB 或 OpenCV/V4L2 |
| 💻 **处理器** | 仅CPU运行 | 无需GPU |
| 🪟 **操作系统** | Windows 或 Ubuntu 24.04 Xorg | 不支持 Wayland |

### ⭐ 核心特性

<div align="left">

| 特性 | 描述 | 图标 |
|------|------|------|
| **基于头姿的四方向选择** | 张嘴打开全屏选择层，按头部移动方向选择机器人动作 | 🎯 |
| **面部表情映射** | 直接输出经过校验的机器人动作词条 | 😊 |
| **多模态控制** | 结合头部方向与面部动作 | 🤖 |
| **可定制配置** | 适用于不同使用场景 | ⚙️ |
| **实时性能** | CPU优化推理 | 🚀 |

</div>

---

## 📊 性能评估

我们使用多个校准数据集进行了渐进式训练的综合测试。系统在经过多次训练后，在3072×1920显示屏上实现了稳定的凝视追踪性能：

### 📈 性能指标

- **平均误差**: **48毫米** (原始)
- **卡尔曼滤波后**: **40毫米** (优化后)
- **显示分辨率**: 3072×1920
- **训练数据**: 多个校准数据集

> 💡 **注意**: 目前性能确实比Tobii的效果差不少，我们欢迎社区一起共创改进！

![渐进式训练分析](results/progressive_training/comprehensive_comparison.png)

*渐进式训练结果显示了多个数据集的误差减少和性能稳定性。分析表明随着更多训练数据的加入，凝视精度持续改善。*

---

## 🚀 快速安装

NeuGaze 使用一条共享 Python 管线，并按平台、摄像头和测试用途增加对应组件。请安装所属平台的完整运行依赖文件，不要逐个挑选包拼装环境。

### 🧩 各依赖组安装什么功能

| 分类 | 主要组件 | 提供的功能 |
|---|---|---|
| 核心视觉与注视 | PyTorch、TorchVision、NumPy、MediaPipe、OpenCV、ONNX Runtime、NCNN | 人脸检测、表情识别、注视估计和模型推理 |
| 校准与状态 | scikit-learn、FilterPy、jsonlines、PyYAML | 校准回归、注视平滑、记录和配置解析 |
| GUI 与桌面集成 | PySide6；Ubuntu 使用 `python-xlib`；Windows 使用 PyWin32 | 配置界面、透明层、轮盘和平台桌面接口 |
| 摄像头 | Gemini 335 使用 `pyorbbecsdk2`；Linux 普通视频设备使用 OpenCV/V4L2 | 从明确选择的后端读取 RGB 图像 |
| 机器人词条输出 | Python 标准库；连接 SONIC 时使用 `pyzmq` | Ubuntu 可打印动作词条或请求 SONIC 播放 reference motion |
| 开发测试 | pytest；隔离 X11 测试使用 Xvfb/Xauth | 可选自动化测试，不属于 NeuGaze 日常运行依赖 |

`requirements-ubuntu.txt` 是可复现的完整 Ubuntu 运行锁。Torchaudio 和 tqdm 没有被主 GUI 路径直接导入，但在运行环境与模型转换环境完成拆分及全新安装验证前仍保留固定版本。当前安全的精简方式，是在日常运行时不安装测试依赖和 Xvfb/Xauth。摄像头后端及模型转换包的拆分需要单独执行全新安装验证；不要手工删改运行锁。

### 1. 创建 Conda 环境

两个平台使用相同 Python 版本：

```bash
conda create -n neugaze python=3.11.11
conda activate neugaze
```

### 2. Windows 运行组件

`requirements.txt` 安装 Windows 桌面/游戏输出后端和共享注视管线。使用以下明确命令安装：

```bash
python -m pip install -r requirements.txt
python config_gui_cpu.py
```

### 3. Ubuntu 24.04 运行组件

#### 3.1 Xorg 与 GUI 组件

在登录界面的齿轮菜单选择 **Ubuntu on Xorg**。NeuGaze 不支持 Wayland。X11 后端需要 XTest 和 XFixes；`libxcb-cursor0` 支持 Qt GUI；启用凝视透明层时需要 `xcompmgr`。

只读安装检查器会报告缺失的主机组件。仅当检查器明确报告缺失时才安装系统包：

```bash
export NEUGAZE_ORBBEC_SDK_ROOT=/absolute/path/to/OrbbecSDK_v2
python scripts/check_ubuntu_install.py \
  --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" \
  --require-overlay

sudo apt-get update
sudo apt-get install --no-install-recommends xcompmgr libxcb-cursor0
```

NeuGaze 日常诊断和运行命令不使用 `sudo`。

#### 3.2 Python 运行组件

安装完整 CPU 运行锁，然后移除两个上游包传递安装的冲突 OpenCV wheel：

```bash
python -m pip install -r requirements-ubuntu.txt
python -m pip uninstall -y opencv-python
python -m pip install --no-deps --force-reinstall \
  opencv-contrib-python==4.11.0.86
```

这一步会安装上表中的核心视觉、模型推理、校准、GUI、X11 和两个摄像头后端。

#### 3.3 摄像头组件

在 GUI 中明确选择一个后端；后端失败后 NeuGaze 不会静默切换到另一个后端。

- **Orbbec SDK / Gemini 335：**使用 `pyorbbecsdk2==2.1.1` 及其内置 SDK 2.8.6。`NEUGAZE_ORBBEC_SDK_ROOT` 只提供权威 udev 规则安装器；另行安装的系统 SDK 2.9.3 不是运行前置条件。
- **OpenCV / V4L2：**使用选中的 `/dev/videoN`，运行时不需要 Orbbec udev 规则。

若检查器报告 Gemini 335 udev 规则缺失或不一致，只安装指定 SDK 源码树中的规则，然后重新检查：

```bash
sudo "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/install_udev_rules.sh"
python scripts/check_ubuntu_install.py \
  --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" \
  --require-overlay
```

#### 3.4 验证并启动

运行时诊断会检查 Xorg、X11 扩展、合成器、模型文件、选中的摄像头，以及 Orbbec wheel/SDK ABI。它是只读命令，任何前置条件错误都会明确失败。

```bash
python scripts/check_ubuntu_runtime.py \
  --config configs/cpu.yaml \
  --require-overlay
python config_gui_cpu.py
```

不要使用 `LD_LIBRARY_PATH`、`LD_PRELOAD`、替换库文件或摄像头后端回退来掩盖诊断失败。

### 4. 可选开发与硬件测试组件

NeuGaze 日常运行不需要 pytest、Xvfb 或 Xauth。

```bash
python -m pip install -r requirements-dev.txt
sudo apt-get install --no-install-recommends xvfb xauth
```

连接 Gemini 335 后，显式硬件测试会读取 100 帧、关闭设备、重新打开并再读取一帧：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v
```

### 5. 已知 OpenCV 元数据提示

<details>
<summary>为什么 <code>python -m pip check</code> 会报告两个缺失依赖</summary>

`pyorbbecsdk2==2.1.1` 和 `ncnn==1.0.20260526` 声明依赖分发名 `opencv-python`，而 NeuGaze 有意安装 `opencv-contrib-python==4.11.0.86`。两个 wheel 拥有相同的 `cv2` 文件，不能同时安装。

因此，`python -m pip check` 预期以 1 退出并报告：

```text
pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.
ncnn 1.0.20260526 requires opencv-python, which is not installed.
```

这是包元数据例外，不是 `cv2` 运行库缺失。不要安装 alias/dummy 包、改写已安装元数据或恢复 `opencv-python`；应以运行时诊断和硬件测试作为可执行验证。

</details>

---

## 🎮 快速开始

### 📹 视频教程

可以观看这个视频快速了解系统使用方法：

![快速上手](assets/demo.gif)

### 📋 步骤指南

#### 1️⃣ 启动图形界面

```bash
python config_gui_cpu.py
```

#### 2️⃣ 摄像头设置

- 📷 选择摄像头（默认：摄像头0）
- 👤 将面部位置调整到预览窗口中央
- ✅ 点击"确认选择"

![摄像头选择](assets/camera%20selection.png)

#### 3️⃣ 校准过程

- 🎯 点击"开始校准"
- 👁️ 用眼睛跟随屏幕上的点
- 👀 保持眼睛睁开（只有检测到眼睛时才拍照）
- ⏳ 等待校准完成

#### 4️⃣ 开始控制

- 点击"开始评估"；识别在独立子进程运行，配置标签页仍可切换和操作。运行期间相机切换、重新标定等资源冲突按钮会禁用，"开始评估"按钮变为 "Stop Evaluation"
- 成功完成一次标定后，GUI 会把生成的 `model.pkl` 路径写入 `regression_model_path`；以后重新启动程序可以直接点击"开始评估"，不必每次重新标定
- 张嘴打开前进/后退/左转/右转轮盘；释放后转头选择，回正后再次张嘴提交
- 抬内眉打开挥手/舞蹈/左右横移轮盘；放松眉毛后转头选择，回正后再次抬眉提交
- 嘟嘴或仅闭左眼可直接触发机器人动作词条
- Ubuntu 终端打印 `[ROBOT_ACTION]`，不发送键盘或鼠标事件

只有模型文件不存在、换了使用者、摄像头位置明显变化，或屏幕分辨率/缩放及显示器布局改变时，才建议重新标定。模型加载失败会保留原始文件错误，不会自动使用未标定模型。

---

## 😊 表情与控制配置

NeuGaze 使用 `configs/cpu.yaml` 中的 `expression_evaluator_config` 识别表情，再由
`robot_action_config` 将识别结果映射为机器人动作词条。`robot_action_output_config`
显式选择只打印到 Terminal，或通过本机 IPC 请求 SONIC 执行动作。

### 🎭 表情检测

系统通过 MediaPipe blendshape 识别面部动作。下表是当前 Ubuntu 默认配置的完整
机器人输出契约：

#### 核心表情映射

| 用户动作 | MediaPipe 条件 | 内部表达式 ID | Ubuntu 当前行为 |
|----------|-----------------|----------------|-----------------|
| **张嘴** | `jawOpen > 0.4`，且下颌没有明显左右偏移 | `numlock` | 第一次张嘴打开透明全屏四分区选择层；稳定选择方向并回正后，再次张嘴提交 |
| **嘟嘴** | `mouthPucker > 0.97` 且 `mouthFunnel < 0.2` | `left_click` | 输出 `wave` / **挥手** |
| **抬内眉** | `browInnerUp > 0.8` | `num8` | 第一次抬眉打开透明全屏四分区选择层；稳定选择方向并回正后，再次抬眉提交 |
| **仅闭左眼** | `eyeBlinkLeft > 0.6` 且 `eyeBlinkRight < 0.25` | `extra` | 输出 `stop` / **停止** |

`left_click`、`num8`、`extra` 和 `numlock` 是沿用的内部表达式 ID，不代表 Ubuntu
会点击鼠标或发送对应键盘按键。下颌左右移动和左右/双侧微笑虽然仍可被表情评估器
识别，但当前没有配置直接机器人动作。头部俯仰和偏航专用于张嘴或抬眉打开的四方向选择。

#### 表情阈值设置

可以通过这个程序来查看做一些表情时的分数，从而自己调整阈值。

```cmd
python learn\mediapipe_example.py
```

#### 表情配置示例

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

### 🤖 Ubuntu 机器人动作输出

Ubuntu 使用机器人动作输出路径，不使用 `game`、`game_cs`、`game_wz` 或 `type` 的
键位表。默认 `terminal` 只打印；`sonic_ipc` 等待 SONIC 明确确认后再打印成功行，
也不会发送桌面键盘/鼠标事件。

#### 直接表情动作

直接表情在从未触发变为已触发的上升沿输出一次；持续保持表情不会重复刷屏。

| 内部表达式 ID | 动作 ID | 终端标签 | 来源 |
|---------------|---------|----------|------|
| `left_click` | `wave` | **挥手** | `expression` |
| `extra` | `stop` | **停止** | `expression` |

#### 张嘴加头部方向的全屏四分区选择层

| 头部方向 | 动作 ID | 终端标签 |
|----------|---------|----------|
| **抬头** | `move_forward_step` | **前进** |
| **低头** | `move_backward_step` | **后退** |
| **向左转头** | `turn_left` | **左转** |
| **向右转头** | `turn_right` | **右转** |

使用顺序：

1. 第一次张嘴触发 `numlock`，打开覆盖整个主屏幕的透明选择层；第一次张嘴只负责打开轮盘，随后可以闭嘴。
2. 转头选择期间不需要持续张嘴。将头部从中立位置向上、下、左或右移动；俯仰超过 `18°` 或偏航超过 `12°` 后，方向必须连续稳定 5 个有效处理帧才会锁定并高亮。两个方向同时超过阈值时，采用相对各自阈值偏移更大的方向。
3. 方向高亮后，把头部回到阈值内的中立死区并保持闭嘴。连续 3 个有效中立帧确认第一次张嘴已经释放后，系统才接受第二次张嘴；已经锁定的高亮不会因回正而清除。
4. 在中立位置再次张嘴连续 5 个有效帧后，系统立即输出锁定的一个动作词条，不需要再闭嘴。人脸或 blendshape 丢失不会提交，并会解除确认资格；恢复跟踪后必须重新完成第 3 步。
5. 尚未锁定任何方向时，先在中立位置保持闭嘴 3 个有效帧，再次张嘴连续 5 个有效帧，只会输出显式取消行，不会伪造动作。提交或取消后必须先释放本次表情，下一次张嘴才会重新打开轮盘。

#### 抬眉加头部方向的全屏四分区选择层

| 头部方向 | 动作 ID | 终端标签 |
|----------|---------|----------|
| **抬头** | `wave` | **挥手** |
| **低头** | `dance` | **舞蹈** |
| **向左转头** | `strafe_left` | **向左横移** |
| **向右转头** | `strafe_right` | **向右横移** |

第一次抬内眉触发 `num8` 并打开第二个透明全屏选择层，随后可以立即放松眉毛；转头选择期间不需要持续抬眉。方向连续稳定 5 个有效处理帧锁定后，头部回到中立死区并保持未抬眉 3 个有效帧，再次抬眉连续 5 个有效帧便立即提交，不需要再次放松眉毛。人脸或 blendshape 丢失不会提交，并会解除确认资格。尚未锁定方向时，以同样的“释放 3 帧 → 再次抬眉 5 帧”只输出显式取消行。提交或取消后必须先放松眉毛，下一次抬眉才会重新打开轮盘。

选择层背景完全透明，不遮挡当前桌面；仅绘制低透明度分区边界。当前头部方向对应的区域显示低透明蓝色高亮，中文动作标签使用 `Noto Sans CJK SC` 字体和深色圆角底板。窗口保持置顶、点击穿透且不获取焦点。全屏分区只提供方向反馈，选择不再使用注视坐标。

#### 终端输出格式

```text
[ROBOT_ACTION] id=wave label=挥手 source=expression
[ROBOT_ACTION] id=stop label=停止 source=expression
[ROBOT_ACTION] id=move_forward_step label=前进 source=wheel
[ROBOT_ACTION] id=move_backward_step label=后退 source=wheel
[ROBOT_ACTION] id=turn_left label=左转 source=wheel
[ROBOT_ACTION] id=turn_right label=右转 source=wheel
[ROBOT_ACTION] id=wave label=挥手 source=wheel
[ROBOT_ACTION] id=dance label=舞蹈 source=wheel
[ROBOT_ACTION] id=strafe_left label=向左横移 source=wheel
[ROBOT_ACTION] id=strafe_right label=向右横移 source=wheel
```

未选中轮盘区域时输出：

```text
[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel
```

这些标签也是 NeuGaze 与 SONIC 之间的稳定动作标识。SONIC 持有动作 ID 到 reference
motion 目录的映射；NeuGaze 不传输 CSV 或逐帧姿态。

### ⚙️ 高级配置

动作 ID、中文标签和表达式绑定只有一个事实来源：`configs/cpu.yaml` 中的
`robot_action_config`。未知动作、缺失动作或非法轮盘配置会在启动时直接报错。

```yaml
robot_wheel_config:
  layout: fullscreen_cardinal
  selection: head_pose
  yaw_threshold_degrees: 12.0
  pitch_threshold_degrees: 18.0
robot_action_output_config:
  type: terminal
robot_action_config:
  actions:
    move_forward_step: 前进
    move_backward_step: 后退
    turn_left: 左转
    turn_right: 右转
    strafe_left: 向左横移
    strafe_right: 向右横移
    wave: 挥手
    dance: 舞蹈
    stop: 停止
  expressions:
    numlock:
      wheel: [move_forward_step, move_backward_step, turn_left, turn_right]
    left_click:
      action: wave
    num8:
      wheel: [wave, dance, strafe_left, strafe_right]
    extra:
      action: stop
```

连接本机 SONIC 时改为：

```yaml
robot_action_output_config:
  type: sonic_ipc
  endpoint: ipc:///tmp/neugaze-sonic.sock
  timeout_ms: 1000
```

`stop` 由仅闭左眼触发，在 `sonic_ipc` 模式下发送
`reset_reference_motion`。它与用户在 SONIC reference-motion 模式测试的 `R` 一致：
停止播放、回到第 0 帧并重新初始化朝向；不是 planner momentum reset，也不是实体机器人的
物理急停。完整 MuJoCo 命令见
[`docs/neugaze-sonic-mujoco-test.md`](docs/neugaze-sonic-mujoco-test.md)。

当前机器人选择层固定为透明全屏四方向布局，并且只接受 `selection: head_pose`。配置不再接受 `radius`；布局、选择方式、阈值字段缺失、未知或非法时，程序会在启动时明确报错。`yaw_threshold_degrees` 和 `pitch_threshold_degrees` 是相对 `head_angles_center` 的角度阈值，合法范围为 `(0, 45]`。头部动作不会映射到 W/S、A/D 或滚轮。

---

## 🎯 使用场景

### ♿ 无障碍辅助

- **🦽 行动辅助**: 为行动不便的用户提供免手计算机操作
- **🏥 康复训练**: 通过控制头部和面部动作进行运动技能训练

### 🤖 机器人控制

- **动作词条验证**: 在终端检查表情识别和轮盘选择是否正确
- **参考动作接入**: 将九个稳定动作 ID 映射到 GR00T/WBC reference motion

### 🤖 智能设备集成

- **🥽 AR/VR界面**: 头戴显示设备的自然控制
- **👓 智能眼镜**: 基于表情的导航，无需手势

---

## ⚙️ 技术细节

### 🏗️ 架构

| 组件 | 功能描述 | 技术实现 |
|------|----------|----------|
| **🎯 意图识别** | 对面部表情、头部动作和凝视模式的综合分析 | MediaPipe + 自定义算法 |
| **🔄 意图映射** | 将表情和轮盘选区转换为稳定机器人动作 ID | `robot_action_config` |
| **🎭 多模态融合** | 多个同时意图的集成和优先级处理 | 优先级规则引擎 |
| **⚡ 动作输出** | 打印动作 ID、中文标签和来源 | `[ROBOT_ACTION]` 终端协议 |
| **🚀 优化** | 为实时性能优化的CPU推理管道 | CPU优化推理 |

### ⚠️ 局限性

| 限制 | 影响 | 解决方案 |
|------|------|----------|
| **🌞 光照敏感性** | 在光照不良或不均匀时性能下降 | 调整环境光照 |
| **🎯 需要校准** | 需要个人校准以获得最佳精度 | 定期重新校准 |
| **📚 表情学习** | 自然表情控制存在学习曲线 | 练习和适应 |

---

## 🤝 贡献

我们欢迎贡献！请随时提交问题、功能请求或拉取请求。

### 🎯 贡献方式

- 🐛 **报告问题**: 提交Bug报告
- 💡 **功能建议**: 提出新功能想法
- 🔧 **代码贡献**: 提交Pull Request
- 📚 **文档改进**: 帮助完善文档

---

## 📄 许可证

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

本项目采用知识共享署名-非商业性使用4.0国际许可证。

### ✅ 您可以自由地：

- ✅ 个人使用时分享和改编代码
- ✅ 用于研究和教育目的
- ✅ 为非商业目的创建衍生作品（如直播、内容创作）

### ❌ 您不可以：

- ❌ 销售源代码或衍生作品
- ❌ 部署为商业硬件/软件产品
- ❌ 打包为付费可执行应用程序
- ❌ 用于商业网络服务

> 💡 **说明**: 我们免费提供此软件以造福社区，同时防止商业实体的剥削。许可条款可能根据社区反馈更新为Apache-2.0或MIT协议。

---

## 📚 引用

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

**⚠️ 注意**: 本系统专为研究和无障碍目的设计。虽然功能完备，但可能需要个人调整以获得最佳性能。我们鼓励实验并欢迎反馈以改进系统的稳健性和可用性。

---

⭐ **如果这个项目对您有帮助，请给我们一个星标！** ⭐

</div>
