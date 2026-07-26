# NeuGaze Ubuntu 24.04 Xorg 移植设计

## 目标

让 NeuGaze 在 Ubuntu 24.04 Xorg 会话中完整运行，同时保留现有 Windows 支持。Ubuntu 版本覆盖 GUI、Orbbec SDK 与 OpenCV/V4L2 摄像头、校准、凝视鼠标、表情键鼠映射、轮盘和透明凝视层；当前默认摄像头是 Orbbec Gemini 335。安装阶段可在用户批准后使用 `sudo`，日常运行不得要求 root。

本次只迁移 README 描述的 GUI 主路径和 `my_model_arch/cpu_fast` 生产路径，不迁移 `learn/` 下的实验脚本。

协作进度统一记录在 `docs/ubuntu-xorg-port-progress.md`。实施者必须在任务状态、验证结果或阻塞条件变化后更新该文件。

## 设计原则

- source-of-truth 链路 fail fast，不返回伪成功、空帧、旧缓存或默认输入。
- 不在 X11 能力缺失时切换到 Wayland、主线程实现或外部命令。
- 不在摄像头后端失败时切换到另一个后端。
- 平台接口只覆盖当前程序真实使用的能力，不新增 manager、factory 或通用设备框架。
- Windows 与 X11 实现显式分离，公共推理和控制算法不包含系统 API。
- 后台线程和凝视层进程的异常必须回到主管线并保留原始 traceback。

## 支持范围

### Ubuntu

- Ubuntu 24.04 x86-64
- Xorg 会话
- Python 3.11
- CPU 推理
- Orbbec Gemini 335
- Orbbec SDK v2 RGB 彩色流，以及普通 OpenCV/V4L2 彩色摄像头
- 日常运行不使用 root

### Windows

保留当前 OpenCV/DirectShow 摄像头路径和 Win32 输入能力。平台拆分不得改变现有配置键和用户可见控制语义。

### 不支持

- Wayland
- Orbbec SDK 与 OpenCV/V4L2 之间的自动选择或故障回退
- Gemini 335 深度流与红外流
- `learn/` 实验脚本的跨平台迁移
- 无显示服务器的正式运行

## 平台结构

新增 `my_model_arch/cpu_fast/desktop` 包：

- `desktop/__init__.py` 根据 `sys.platform` 导出唯一实现。未知平台立即抛出 `UnsupportedPlatformError`。
- `desktop/win32.py` 承接现有 Win32 屏幕、光标和键鼠能力。
- `desktop/x11.py` 使用 `python-xlib`、XTest 和 XFixes 实现 Ubuntu 能力。

平台模块只提供以下语义：

- 验证桌面会话与必需扩展
- 查询屏幕尺寸
- 查询一个或一组按键状态
- 按下与释放键盘按键
- 绝对与相对移动指针
- 按下与释放鼠标按钮
- 滚轮操作
- 查询光标是否可见

`GazeMouseController` 保留凝视和头部控制算法，只将 Win32 和 `pyautogui` 调用替换为平台函数。`RealAction` 和 GUI 热键检测也使用同一平台函数。

Linux 启动时验证：

1. `DISPLAY` 存在并能连接。
2. `XDG_SESSION_TYPE` 未声明为 `wayland`。
3. XTest 扩展可用。
4. XFixes 扩展可用。
5. 启用透明凝视层时存在 X11 合成管理器。

任一检查失败时，错误必须包含失败条件和当前环境值。

## X11 输入

X11 后端维护一个受锁保护的 Display 连接，所有请求完成后显式 flush。它使用 XTest 发送键鼠事件，使用 X11 键盘映射查询当前状态。

按键名称按当前 XKB 布局解析。普通字母、数字、功能键、修饰键、导航键、标点和现有配置中的鼠标按钮都必须覆盖。字符需要修饰键时，解析结果同时包含对应修饰键。配置中的名称无法映射时抛出包含键名和当前布局信息的错误。

安全按下只在目标键当前未按下时发送按下事件。安全释放在超时前查询状态并重复发送释放；超时后抛出 `TimeoutError`。退出路径释放 NeuGaze 自己记录为按下的键和鼠标按钮，不释放未由 NeuGaze 持有的物理输入。

光标可见性通过 XFixes `GetCursorImage` 返回像素的 Alpha 通道判断。无法查询或响应格式异常时抛错，不默认返回可见或隐藏。

## 透明凝视层

Windows 保留当前 Win32 覆盖层。Ubuntu 使用 PySide6 创建：

- 全屏
- 无边框
- 置顶
- 背景透明
- 输入穿透
- 不获取焦点

当前评估循环会阻塞 GUI 事件循环，因此 Ubuntu 覆盖层运行在一个专用进程中。父进程启动后等待明确的 ready 或 error 消息；初始化超时或子进程异常会终止启动。子进程返回格式化的原始 traceback，父进程在主管线中抛出。

坐标通道只保留最新凝视点，这是显示帧合并规则，不改变预测、校准数据或配置。父进程在每次更新和主管线循环中检查子进程存活状态。覆盖层停止必须等待子进程退出；超时即报错，不遗留后台进程。

## Ubuntu 摄像头后端

YAML 对每个平台保存明确后端，不根据已连接设备推断：

```yaml
integrated_config:
  camera_backend:
    linux: orbbec
    win32: opencv
  cam_id: 0
  camera_width: 1280
  camera_height: 720
  camera_fps: 30
```

`camera_backend.linux` 只接受 `orbbec` 或 `opencv`，`camera_backend.win32` 本次固定为 `opencv`。当前平台键缺失、值未知或类型错误时，配置加载立即失败。

Ubuntu GUI 提供 `Orbbec SDK` 和 `OpenCV / V4L2` 两项。切换后端会先停止并释放当前预览，再使用对应 API 重新枚举设备。GUI 和 YAML 始终显示并保存当前平台的明确选择。

主管线通过两个直接实现取得相同的 BGR `numpy.ndarray` 读帧结果。后端分派只有一个显式 `if/elif`，不注册插件、不扫描能力、不捕获一个后端的错误后调用另一个后端。

### Orbbec Gemini 335 RGB

2026-07-26 用户明确批准 ABI 选项 A：Ubuntu Python 权威运行时分发必须是 `pyorbbecsdk2==2.1.1`，`pyorbbecsdk.get_version()` 必须返回 SDK 2.8.6，且导入扩展经 `ldd` 解析的 `libOrbbecSDK.so.2` 必须位于该 `pyorbbecsdk` 包目录内。解析到系统 `/usr/local/lib/libOrbbecSDK.so.2.9.3`、其他路径/版本或其他 SDK 版本时立即失败。系统 SDK 2.9.3 保持不变，仅作为信息发现，不是 Python 运行前置条件；禁止修改隐式库搜索路径、替换库或增加构建回退。

新增 `OrbbecColorCamera`，其职责仅为 Gemini 335 RGB 采集：

1. 用 `Context.query_devices()` 枚举设备。
2. GUI 显示设备型号、序列号和设备索引。
3. 用选择的 Device 创建 `Pipeline(device)`。
4. 只启用 `1280x720 @ 30 FPS`、`OBFormat.RGB` 彩色流。
5. `read()` 最多等待 1000 ms。
6. 将 RGB 数据转换成 shape 为 `(720, 1280, 3)`、dtype 为 `uint8`、C-contiguous 的 BGR 数组。
7. `release()` 精确停止一次 Pipeline。

GUI 预览、校准和评估共享该实现，但同一时间只有一个所有者可以打开设备。预览切换到校准或评估前必须先成功停止并释放。

以下情况直接抛错并包含设备型号、序列号、索引和流配置：

- 未检测到所选设备
- 无法取得指定 RGB profile
- Pipeline 启动失败
- 1000 ms 内未收到 FrameSet
- FrameSet 缺少彩色帧
- 帧格式、尺寸或数据长度不符
- 设备断开
- Pipeline 停止失败

不返回 `(False, None)`，不重试，不切换 V4L2 或 OpenCV。

Windows 摄像头实现本次不改为 Orbbec SDK。

### OpenCV/V4L2 RGB

Ubuntu 的 OpenCV 后端只使用 `cv2.CAP_V4L2`。GUI 枚举 `/dev/video*`，显示设备路径并保存对应数字索引。打开时按 YAML 中的 `camera_width`、`camera_height` 和 `camera_fps` 设置采集参数，然后读取实际值并验证；设备不接受请求配置时直接报出请求值和实际值。

每次 `read()` 都检查布尔结果、帧是否为 `None`、shape、dtype 和内存连续性。合法帧统一为 C-contiguous BGR `uint8` 数组。打开失败、读帧失败、格式不符和设备断开都直接抛错，不调用 Orbbec SDK。

Windows 继续沿用现有 OpenCV/DirectShow 枚举与读取行为。

## 错误传播与资源生命周期

内部层只在需要补充上下文或执行清理时捕获异常。补充上下文使用异常链保留原始异常；完成清理后重新抛出。

GUI 是用户可见错误边界：显示操作、设备和完整 traceback，然后保持失败状态。GUI 不把初始化失败改写成布尔值供调用方继续执行。

鼠标控制线程保存原始异常和 traceback。主管线每轮调用 `raise_if_failed()`，发现异常立即停止评估并重新抛出。输入 Action 在现有动作顺序中同步执行，避免每个动作创建不可观察的守护线程。

退出顺序：

1. 设置评估停止信号。
2. 停止发送新输入。
3. 释放 NeuGaze 持有的键和鼠标按钮。
4. 停止凝视鼠标线程。
5. 停止透明凝视层。
6. 停止并释放摄像头。
7. 关闭 OpenCV 和轮盘窗口。
8. 关闭 X11 Display 连接。

如果业务异常与清理异常同时出现，保留业务异常为主异常，并把清理异常作为附加上下文输出。

## 依赖与安装

现有 `requirements.txt` 保留为 Windows 依赖集合；本次不新增 Windows 安装器。Ubuntu 新增独立 requirements，至少包含：

- Python 3.11
- CPU 版 PyTorch 2.6.0
- torchvision 0.21.0
- torchaudio 2.6.0
- `python-xlib`
- `pyorbbecsdk2==2.1.1`
- 现有公共推理、GUI 和数值依赖

Ubuntu requirements 不包含 `pywin32`、`keyboard` 或 CUDA wheel。生产路径移除对 `pyautogui` 的依赖后，Ubuntu requirements 也不包含 `pyautogui`。

安装脚本先检查现有 SDK、Conda 环境、系统库、udev 规则和系统包。只有确实缺少需要 root 的项目时才请求用户批准 `sudo`。安装脚本不得自动升级固件、SDK 或操作系统包集合。

## 测试设计

所有行为修改使用测试先行。

### 单元测试

- 平台选择只选择一个实现，未知平台失败。
- XKB 名称解析覆盖当前配置所有键。
- 安全按下、释放、超时和持有集合。
- 光标 Alpha 可见性判定与畸形响应。
- Orbbec RGB 到 BGR 的尺寸、dtype、内存连续性和通道顺序。
- Orbbec 超时、空 FrameSet、缺少彩色帧、错误格式、断连和重复释放。
- `camera_backend` 按平台选择、YAML roundtrip、未知值失败和后端互不回退。
- OpenCV/V4L2 打开失败、请求参数不匹配、空帧、错误格式和断连。
- 鼠标线程与覆盖层子进程异常回传。

外部 SDK 和硬件边界允许使用最小 fake；测试不得只验证 mock 调用次数，必须验证返回帧、状态或错误行为。

### Xvfb 集成测试

- XTest 指针绝对和相对移动。
- 键盘按下、查询和释放。
- 鼠标按钮与滚轮事件。
- 后端初始化和 Display 关闭。
- 在 Xvfb 上启动 `xcompmgr` 后验证覆盖层进程握手、透明绘制和正常停止；合成器未启动时测试必须验证初始化失败。

### Gemini 335 硬件测试

硬件测试通过显式参数启用。启用后：

- 必须识别 Gemini 335。
- 必须成功打开指定 RGB profile。
- 必须连续取得 100 个合法 BGR 帧。
- 必须释放并重新打开设备。

设备缺失、权限不足或读帧失败都计为测试失败，不跳过。

## Ubuntu Xorg 实际验收

1. GUI 显示 Gemini 335 型号和序列号。
2. GUI 可在 Orbbec SDK 与 OpenCV/V4L2 间明确切换，默认选择 Orbbec。
3. Gemini 335 RGB 预览持续稳定。
4. 完成九点校准并进入实时评估。
5. 凝视绝对和相对移动鼠标正常。
6. 左、右、中键、侧键和滚轮正常。
7. 键盘按下、保持、释放、组合键和安全释放正常。
8. 表情映射与轮盘选择正常。
9. 凝视层透明、置顶、输入穿透且不抢焦点。
10. ESC+Q 停止评估并释放所有资源。
11. 断开 Gemini 335 时显示原始错误并终止操作。
12. 选择 OpenCV/V4L2 时可预览普通 USB 摄像头，断开时只报告 V4L2 错误。
13. 日常运行过程不使用 root。

## 参考资料

- Orbbec Python Application Guide: <https://orbbec.github.io/pyorbbecsdk/source/5_Application_Guide/ApplicationGuide.html>
- pyorbbecsdk2 PyPI: <https://pypi.org/project/pyorbbecsdk2/>
- python-xlib XFixes: <https://github.com/python-xlib/python-xlib/blob/master/Xlib/ext/xfixes.py>
- Qt translucent widgets: <https://doc.qt.io/qt-6.5/qwidget.html>
- Qt window flags: <https://doc.qt.io/qt-6.5/qt.html>
