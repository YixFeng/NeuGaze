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

用这个系统可以完成复杂的动作游戏的操控，如视频中展示的黑神话悟空打败寅虎。还可以用来玩王者荣耀这种MOBA游戏，CS2等FPS游戏。

<div align="left">
    <h3>NeuGaze wukong</h3>
    <video src="https://github.com/user-attachments/assets/2b604e6e-7468-470c-a3df-afc302ffedb0" />
</div>
---

我们正在举办全球 CS2 军备竞赛挑战赛：冠军奖金 2000 RMB。首位完成环境配置、在军备竞赛人机模式达成击杀并录制教程者，额外奖励 500 RMB。



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
| **基于凝视的鼠标控制** | 实时校准，精确追踪 | 🎯 |
| **面部表情映射** | 键盘/鼠标操作映射 | 😊 |
| **三模态控制** | 结合凝视、表情和头部动作 | 🎮 |
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

### 🎯 推荐安装方式

#### Windows用户
```cmd
# 双击运行安装脚本
install.bat
```

<details>
<summary>📋 脚本功能详情</summary>

脚本会自动执行以下操作：
1. ✅ 检查Python版本和conda环境
2. ✅ 创建名为 `neugaze` 的conda环境
3. ✅ 指导你激活环境并安装依赖
4. ✅ 验证安装是否成功

</details>

#### Ubuntu 24.04 用户（Xorg）

在登录界面选择用户后，点击齿轮菜单并选择 **Ubuntu on Xorg**，再进入
桌面；NeuGaze 不支持 Wayland。Ubuntu 主机需要 XTest、XFixes；需要凝视
透明层时还必须运行 `xcompmgr` 等 X11 合成管理器，并安装
`libxcb-cursor0` 与 Gemini 335 设备访问所需的 Orbbec udev 规则。系统库与
udev 规则属于一次性的管理员安装步骤；NeuGaze 日常诊断与运行命令不使用
`sudo`。Python 摄像头权威运行时是 `pyorbbecsdk2==2.1.1` 及其内置 SDK
2.8.6；另行安装的系统 SDK 2.9.3 不是 Python 运行前置条件。

在仓库根目录先创建并激活精确环境，显式指定 Orbbec SDK 源码树绝对
路径，并在安装 Python 包或运行 runtime 诊断之前执行只读安装检查器：

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

安装检查器只逐项报告缺失或不一致的前置条件；它不会安装包、复制规则、
修改权限、重载 udev 或修复主机。若报告 runtime 系统包缺失，必须先取得
用户明确批准，再执行：

```bash
sudo apt-get update
sudo apt-get install --no-install-recommends xcompmgr libxcb-cursor0
```

Xvfb 集成测试工具不是日常运行依赖。安装测试包也必须另行取得批准：

```bash
sudo apt-get install --no-install-recommends xvfb
```

若 Orbbec udev 规则缺失或内容不一致，必须先取得明确批准，然后只运行
所指定 SDK 源码树内的安装器：

```bash
sudo "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/install_udev_rules.sh"
```

验证过程本身保持非特权、只读：

```bash
sha256sum "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules"
cmp --silent "$NEUGAZE_ORBBEC_SDK_ROOT/scripts/env_setup/99-obsensor-libusb.rules" /etc/udev/rules.d/99-obsensor-libusb.rules
python scripts/check_ubuntu_install.py --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" --require-overlay
```

源码规则摘要必须是
`71a727fbe198a93213d6d6a62a91040da87489065420ff01d102d6334c89a25b`。
`NEUGAZE_ORBBEC_SDK_ROOT` 只提供权威 udev 安装器和规则来源，不替换也不
重定向 Python wheel 运行时；权威运行时仍是 `pyorbbecsdk2==2.1.1` 及其内置
SDK 2.8.6。检查通过后执行已批准的 OpenCV 冲突修复，并始终以非 `sudo`
方式启动：

```bash
python config_gui_cpu.py
```

`requirements-ubuntu.txt` 只直接固定
`opencv-contrib-python==4.11.0.86`。它固定的两个上游依赖方仍会传递安装
`opencv-python`，所以每次全新安装或更新 requirements 后都必须执行上方
精确的卸载与 contrib 强制重装命令。不要让 `opencv-python` 与 contrib
同时保留：两个 wheel 拥有同一批 `cv2` 文件。但固定版本的上游 wheel
`pyorbbecsdk2==2.1.1` 与 `ncnn==1.0.20260526` 都无条件声明依赖分发名
`opencv-python`，而 Python 包元数据没有让 contrib wheel 满足另一分发名的
机制。因此 `python -m pip check` 预期以 1 退出，并原样报告以下两条上游
分发名冲突：

```text
pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.
ncnn 1.0.20260526 requires opencv-python, which is not installed.
```

这个经用户批准的上游分发名例外只适用于包元数据。不得过滤它、把
`pip check` 记作通过、安装 alias/dummy 分发、改写已安装 metadata，或恢复
存在文件冲突的 wheel。实际运行验证必须确认 OpenCV 4.11.0 可导入且
metadata 中只存在 `opencv-contrib-python`，MediaPipe 与 Orbbec 可导入，
只读诊断通过，并执行下方显式 Gemini 335 硬件测试。

诊断脚本只读运行，逐项打印所有检查，并在任一前置条件错误时以非零状态
退出。诊断退出 0 前不要启动 GUI。脚本会同时打印
Python 分发必须为 `pyorbbecsdk2==2.1.1`，
`pyorbbecsdk.get_version()` 必须返回 2.8.6，扩展经 `ldd` 解析到的
`libOrbbecSDK.so.2` 必须位于导入的 `pyorbbecsdk` 包目录内。另行安装的
系统 SDK 2.9.3 只作信息展示；解析到该系统库、其他路径/版本或其他 SDK
版本都会失败。禁止用 `LD_LIBRARY_PATH`、`LD_PRELOAD`、替换库文件或自动
回退掩盖偏差。

GUI 中必须明确选择一个 Linux 摄像头后端：

- **Orbbec SDK**：枚举型号和序列号，并使用选中的 Gemini 335 索引；
- **OpenCV / V4L2**：使用选中的 `/dev/videoN` 设备。

后端或设备失败会直接显示；NeuGaze 不会自动切换到另一后端。硬件验收
命令使用 pytest，因此执行前先安装开发依赖；正常运行 NeuGaze 不需要这些
依赖：

```bash
python -m pip install -r requirements-dev.txt
```

连接 Gemini 335 后，用以下显式命令验证读取 100 帧、关闭、重开并再读一帧：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v
```

### 🔧 手动环境配置（Windows）

```bash
# 创建并激活conda环境
conda create -n neugaze python=3.11.11
conda activate neugaze

# 安装所有依赖
pip install -r requirements.txt
```

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

- 🎮 点击"开始评估"
- 🖱️ 鼠标光标现在将跟随您的凝视
- 😊 使用面部表情触发操作

---

## 😊 表情与控制配置

NeuGaze使用在 `configs/cpu.yaml`中定义的复杂表情识别系统。系统支持多种控制模式和可定制映射。

### 🎭 表情检测

系统通过MediaPipe关键点识别面部表情并将其映射到特定操作：

#### 核心表情映射

| 表情 | 动作描述 | 触发操作 |
|------|----------|----------|
| **张嘴** (`jawOpen`) | *自然地张开下颌* | 🎯 模式选择器 - 显示可用控制轮盘 |
| **嘟嘴** (`mouthPucker`) | *做出亲吻动作，嘴唇撅起* | 🖱️ 鼠标左键点击 |
| **下颌左移** (`jawLeft`) | *将下颌向左侧移动* | 🖱️ 鼠标右键点击 |
| **下颌右移** (`jawRight`) | *将下颌向右侧移动* | 🖱️ 鼠标中键点击 |
| **左侧微笑** (`mouthSmileLeft`) | *只用嘴的左侧微笑* | 🧭 导航/选择 |
| **右侧微笑** (`mouthSmileRight`) | *只用嘴的右侧微笑* | 🧭 导航/选择 |
| **双侧微笑** | *自然的双侧完整微笑* | ⚡ 特殊命令 |
| **头部动作** | *倾斜、转动和点头* | ⌨️ WASD键和滚动 |

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

### 🎮 控制模式

系统通过轮盘界面支持多种操作模式：

#### 🎯 1. 黑悟空游戏模式 (`game`)

针对游戏优化，包含WASD移动和常用游戏键：

| 轮盘位置 | 按键映射 | 功能描述 |
|----------|----------|----------|
| **num1** | Z/X/C键 | 🎮 切棍操作 |
| **num2** | Shift键 | 🏃 冲刺/蹲下 |
| **num4** | 数字键1-4 | ⚔️ 技能选择 |
| **num6** | Q/R/F/T键 | 🎯 操作选择 |
| **num8** | 空格键 | ⚡ 闪避 |

#### 🎯 2. CS:GO模式 (`game_cs`)

专为反恐精英设计的战术绑定：

| 轮盘位置 | 按键映射 | 功能描述 |
|----------|----------|----------|
| **num2** | 空格键 | ⬆️ 跳跃 |
| **num8** | Shift键 | 🚶 走路/精确射击 |
| **鼠标锁定** | 禁用 | 🎯 实现精确瞄准 |

#### 🎯 3. 王者荣耀模式 (`game_wz`)

针对MOBA游戏优化：

| 轮盘位置 | 按键映射 | 功能描述 |
|----------|----------|----------|
| **num1-3** | 技能激活 | ⚔️ 技能1-3 |
| **num4** | M键 | 🗺️ 地图 |

#### ⌨️ 4. 打字模式 (`type`)

完整键盘访问用于文本输入：

| 轮盘位置 | 按键映射 | 功能描述 |
|----------|----------|----------|
| **num4** | 完整字母表 | 🔤 方形布局的字母 |
| **num6** | 数字和符号 | 🔢 方形布局的数字和符号 |
| **num2** | 修饰键 | ⌨️ Shift、Ctrl、Alt等 |
| **num3** | 常用快捷键 | 📋 Ctrl+C、Ctrl+V等 |

### ⚙️ 高级配置

#### 🎯 表情优先级

系统包含优先级规则以防止冲突表情：

```yaml
priority_rules:
- when: num7
  disable: [num2]
  except: []
```

#### 🎨 轮盘布局

不同输入模式支持不同的轮盘布局：

| 布局类型 | 描述 | 适用场景 |
|----------|------|----------|
| **默认** | 圆形排列 | 🎮 游戏模式 |
| **方形** | 网格布局 | ⌨️ 字母和符号输入 |

#### 🎯 头部动作集成

头部方向控制附加功能：

| 头部动作 | 按键映射 | 功能描述 |
|----------|----------|----------|
| **俯仰（上/下）** | W/S键 | ⬆️⬇️ 上下移动 |
| **偏航（左/右）** | A/D键 | ⬅️➡️ 左右移动 |
| **翻滚（倾斜）** | 滚轮 | 🔄 滚动操作 |

---

## 🎯 使用场景

### ♿ 无障碍辅助

- **🦽 行动辅助**: 为行动不便的用户提供免手计算机操作
- **🏥 康复训练**: 通过控制头部和面部动作进行运动技能训练

### 🎮 游戏娱乐

- **🎯 沉浸式游戏**: 为增强游戏体验提供新颖输入方法
- **💪 肌肉训练**: 通过交互控制进行面部和颈部肌肉锻炼

### 🤖 智能设备集成

- **🥽 AR/VR界面**: 头戴显示设备的自然控制
- **👓 智能眼镜**: 基于表情的导航，无需手势

---

## ⚙️ 技术细节

### 🏗️ 架构

| 组件 | 功能描述 | 技术实现 |
|------|----------|----------|
| **🎯 意图识别** | 对面部表情、头部动作和凝视模式的综合分析 | MediaPipe + 自定义算法 |
| **🔄 意图映射** | 将识别的意图转换为特定的键盘/鼠标操作 | 配置驱动的映射系统 |
| **🎭 多模态融合** | 多个同时意图的集成和优先级处理 | 优先级规则引擎 |
| **⚡ 动作执行** | 协调控制系统，实现复杂的游戏操作 | 实时控制接口 |
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
