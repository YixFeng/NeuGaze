# Ubuntu 24.04 Xorg 移植进度

最后更新：2026-07-24

## 协作规则

- 本文件是 Ubuntu 移植的共享进度入口。
- agent 开始工作前先阅读设计、实施计划和本文件。
- 每次任务状态、验证证据、阻塞项或接口约定变化后更新本文件。
- 不把“代码已写”视为完成；只有对应验证通过后才能标记完成。
- 不隐藏错误，不记录未经命令输出支持的“已通过”状态。

## 文档入口

- 设计：`docs/superpowers/specs/2026-07-23-ubuntu-xorg-port-design.md`
- 实施计划：`docs/superpowers/plans/2026-07-24-ubuntu-xorg-port.md`
- 本进度：`docs/ubuntu-xorg-port-progress.md`

## 已确认决策

- 目标系统：Ubuntu 24.04 x86-64
- 桌面会话：Xorg
- Windows：保留现有支持
- 功能范围：GUI、预览、校准、评估、凝视鼠标、完整键鼠映射、轮盘、透明凝视层
- Ubuntu 摄像头后端：明确选择 `orbbec` 或 `opencv`，不自动切换
- 当前默认摄像头：Orbbec Gemini 335
- 摄像头数据：仅 RGB，`1280x720 @ 30 FPS`
- Ubuntu 摄像头 API：Orbbec SDK v2 + `pyorbbecsdk2`
- Ubuntu 普通摄像头 API：OpenCV + V4L2
- Windows 摄像头：本次不改
- 权限：安装阶段需要 `sudo` 时先请求用户；运行阶段不使用 root
- 失败策略：fail fast，无摄像头后端互相切换、Wayland、主线程或旧缓存回退
- 实验目录：不迁移 `learn/`

## 已发现环境

- NeuGaze 仓库：`/home/yixiao/Users/yixiao/Misc/NeuGaze`
- Ubuntu：24.04，内核 `6.14.0-27-generic`
- 当前 shell Python：3.13.9
- 目标 Conda 环境：`/home/yixiao/miniconda3/envs/neugaze`
- Orbbec SDK 源码：`/home/yixiao/Users/yixiao/Misc/OrbbecSDK_v2`
- Orbbec SDK 源码提交：`869ae2d0`
- Orbbec SDK 系统库：`/usr/local/lib/libOrbbecSDK.so.2.9.3`
- Orbbec SDK 安装目录：`/opt/OrbbecSDK_v2.9.3`
- Python Orbbec 绑定：`pyorbbecsdk2==2.1.1`（包版本 2.1.1，SDK 版本 API 报告 2.8.6）
- 仓库初始状态：`main` 与 `origin/main` 同步，开始设计时无本地改动

## 阶段状态

| 阶段 | 状态 | 验证 |
|---|---|---|
| 仓库与平台依赖摸底 | 完成 | 已记录 Win32、DirectShow、pywin32、keyboard、透明层和屏幕 API 调用 |
| 需求确认 | 完成 | 用户批准 Xorg、双平台、完整功能、非 root 运行和 Gemini 335 RGB |
| 设计评审 | 完成 | 用户分三部分批准设计 |
| 设计文档 | 完成 | 摄像头后端修订提交 `62dc98a`，用户已批准 |
| 实施计划 | 完成 | 8 个 TDD 任务已写入，提交 `6bf86ed`，待选择执行方式 |
| 实现 | 进行中（Task 1–4 完成） | X11 后端纯测试与隔离 Xvfb 集成通过；双摄像头源、平台选择器和平台中立动作单元测试通过；Gemini 335 101 帧、关闭重开实机测试已验证 |
| 自动化验证 | 进行中 | Task 4：纯测试 48 passed、Xvfb 集成 13 passed、安全集合 98 passed / 14 deselected、Xvfb 完整默认集合 111 passed / 1 deselected |
| Gemini 335 实机验收 | 未开始 | 需要连接设备和 Xorg 会话 |

## 任务进度

| 任务 | 状态 | 验证 |
|---|---|---|
| Task 1：测试基座与显式摄像头配置 | 完成 | 配置边界的 10 个测试通过 |
| Task 2：Fail-fast OpenCV/V4L2 与 Orbbec RGB 源 | 完成（有 SDK ABI 偏差） | 33 个 Task 1/2 单元测试通过；Gemini 335 读取 100 帧、关闭、重开后再读 1 帧通过 |
| Task 3：平台中立动作与显式桌面选择 | 完成 | selector/action 17 个测试通过（含 cleanup/lifecycle 并发回归）；common modules 编译通过；完整默认测试 50 passed / 1 deselected |
| Task 4：X11/XTest/XFixes 后端 | 完成（formal review 修复） | 纯测试 48 passed；隔离 Xvfb 集成 13 passed；安全集合 98 passed / 14 deselected；Xvfb 完整默认集合 111 passed / 1 deselected |

## 当前工作

Task 4 已完成直接 X11/XTest/XFixes 后端、纯测试和隔离集成测试；所有注入测试仅在 `xvfb-run` 隔离显示中执行，未触碰实时 `DISPLAY=:1`。下一步执行实施计划 Task 5，将摄像头与桌面边界接入生产管线。

## 验证日志

| 日期 | 命令或检查 | 结果 |
|---|---|---|
| 2026-07-23 | `uname -a` | Ubuntu 24.04 系列内核，x86-64 |
| 2026-07-23 | 仓库 Windows 依赖扫描 | 主路径包含 pywin32、WinDLL、DirectShow、Win32 overlay 与输入调用 |
| 2026-07-23 | Orbbec 目录与系统库扫描 | 找到源码、v2.9.3 系统安装和 udev 规则 |
| 2026-07-23 | 所有 Conda 环境检查 `pyorbbecsdk` | 均未安装 |
| 2026-07-23 | 设计文档占位符、一致性、范围和歧义自检 | 通过，提交 `eec9d8f` |
| 2026-07-24 | 摄像头范围变更 | 用户批准 Ubuntu 明确支持 Orbbec SDK 与 OpenCV/V4L2，默认 Orbbec 且禁止互相回退 |
| 2026-07-24 | 摄像头后端设计自检 | 占位符、内部一致性、范围和歧义检查通过，提交 `62dc98a` |
| 2026-07-24 | 实施计划自检 | 8 个任务覆盖配置、双摄像头后端、Win32/X11、管线、overlay、GUI、依赖与实机验收；占位符扫描通过，提交 `6bf86ed` |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v`（RED） | 预期失败：缺少 `my_model_arch.cpu_fast.camera`，`ModuleNotFoundError` |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py -v`（GREEN） | 10 passed，0.01s |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v` | 10 passed，0.01s；系统 ROS pytest 插件自动加载受污染，测试命令必须显式禁用，未安装或隐藏其依赖 |
| 2026-07-24 | 安装 `opencv-python>=4.10.0.84 pyorbbecsdk2==2.1.1` | 安装成功：`opencv-python==4.11.0.86`、`numpy==1.26.4`、`pyorbbecsdk2==2.1.1`；Orbbec wheel 同时安装其声明依赖 |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_sources.py -v`（RED） | 预期失败：缺少 `CameraInfo` 等 Task 2 接口，collection `ImportError` |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_camera_config.py tests/test_camera_sources.py -v`（最终复验） | 33 passed，0.08s |
| 2026-07-24 | 首次 `tests/test_orbbec_hardware.py --run-orbbec -v` | 失败并保留原始错误：`OBError: NULL pointer passed for argument "deviceMgr"`；定位为枚举时未保留 `Context` 生命周期 |
| 2026-07-24 | Orbbec Context 生命周期回归测试 | RED：`RuntimeError: device context was destroyed`；最小修复后 GREEN：1 passed |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v`（最终复验） | 33 passed / 1 deselected，0.08s |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v`（最终复验） | 1 passed，8.35s；Gemini 335 读取 100 帧、关闭、重开并再读 1 帧 |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_orbbec_hardware.py -v` | collection 阶段 1 deselected / 0 selected；未明确传入 `--run-orbbec` 时不触碰硬件 |
| 2026-07-24 | `pyorbbecsdk.get_version()` 与扩展 `ldd` | 包版本 2.1.1，SDK API 报告 2.8.6；扩展解析到 wheel 内 `pyorbbecsdk/libOrbbecSDK.so.2`，未使用系统 v2.9.3 |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_desktop_selection.py tests/test_keyboard_actions.py -v`（RED） | 预期失败：缺少 `my_model_arch.cpu_fast.desktop`，collection `ImportError` |
| 2026-07-24 | 同一 selector/action 命令（GREEN） | 13 passed，0.01s；覆盖两平台惰性选择、全部 `OpType`、未知键错误透传、安全按下/释放及后端异常透传 |
| 2026-07-24 | `/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile my_model_arch/cpu_fast/keyboard_utils.py my_model_arch/cpu_fast/desktop/__init__.py my_model_arch/cpu_fast/desktop/win32.py` | exit 0 |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v` | 46 passed / 1 deselected，0.08s |
| 2026-07-24 | selector close 与 Win32 cleanup 受控交错测试（review RED） | 2 failed / 15 passed；分别复现 close 与已派发操作重叠、cleanup 漏掉注入后尚未记账输入 |
| 2026-07-24 | selector/action review 修复后 focused GREEN | 17 passed，0.24s；另验证 import/close 失败保留原异常与可重试状态 |
| 2026-07-24 | review 修复后 common modules `py_compile` | exit 0 |
| 2026-07-24 | review 修复后完整默认测试 | 50 passed / 1 deselected，0.30s |
| 2026-07-24 | `tests/test_x11_keymap.py -v`（RED） | 预期失败：缺少 `desktop.x11`，collection `ImportError` |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_keymap.py -v`（GREEN） | 39 passed，0.02s；覆盖 Shift level、按键状态位、XFixes Alpha、未知键、生命周期和持有输入清理 |
| 2026-07-24 | X11 新文件 `py_compile` 与 `tests/test_x11_integration.py -m x11 --collect-only -q` | 编译 exit 0；7 tests collected，未连接显示服务器 |
| 2026-07-24 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m 'not x11' -v` | 89 passed / 8 deselected，0.34s；显式排除 X11 集成，未触碰实时显示 |
| 2026-07-24 | `command -v xvfb-run` | exit 1，无输出；未执行 X11 注入集成，Task 4 保持阻塞且未提交 |
| 2026-07-25 | `command -v Xvfb && command -v xvfb-run` | `/usr/bin/Xvfb` 与 `/usr/bin/xvfb-run` 均存在 |
| 2026-07-25 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_integration.py -m x11 -v` | 7 passed，0.21s；初始化/关闭、绝对/相对指针、按键状态、1/2/3/8/9 按钮、轮盘、未知键与 Wayland 拒绝均通过 |
| 2026-07-25 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_x11_keymap.py -v` | 39 passed，0.02s |
| 2026-07-25 | X11 后端、selector、Win32 后端、平台中立动作与两个 X11 测试文件 `py_compile` | exit 0 |
| 2026-07-25 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m 'not x11' -v` | 89 passed / 8 deselected，0.35s |
| 2026-07-25 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v` | 96 passed / 1 deselected，0.52s；首次完整默认集合在隔离 Xvfb 中执行 |
| 2026-07-25 | Task 4 独立 review | 发现并修复：集成测试仅拒绝字面 `:1`、隐式 Shift 所有权重叠错误、按钮 2/3 覆盖缺失；生命周期测试改为 `finally` 关闭 |
| 2026-07-25 | Shift 所有权 focused RED | 2 failed；复现重叠 Shift 提前释放和预先按住 Shift 被错误释放 |
| 2026-07-25 | Shift 所有权 focused GREEN | 2 passed，0.02s；随后增加显式持有 Shift 回归覆盖 |
| 2026-07-25 | 最终 `tests/test_x11_keymap.py -v` | 42 passed，0.02s |
| 2026-07-25 | 最终隔离 `tests/test_x11_integration.py -m x11 -v` | 11 passed，0.20s；增加 Xvfb Xauthority 身份门禁、实时显示别名拒绝及按钮 2/3 事件覆盖 |
| 2026-07-25 | 最终 common `py_compile` | exit 0 |
| 2026-07-25 | 最终 `pytest -m 'not x11' -v` | 92 passed / 12 deselected，0.38s |
| 2026-07-25 | 最终 `xvfb-run -a ... pytest -v` | 103 passed / 1 deselected，0.52s；首次 review 后完整默认集合仅在隔离 Xvfb 中执行 |
| 2026-07-25 | Task 4 formal parent review | Needs fixes：伪造 Xvfb 环境可绕过门禁、显式 Shift 逆序释放、滚轮 release 失败后无清理记录；另补 fresh import 与 lifecycle failure/retry 测试 |
| 2026-07-25 | formal review focused RED：Shift/scroll | 3 failed；分别复现逆序 Shift、Shift transfer flush 失败状态、滚轮 release 失败后记录丢失 |
| 2026-07-25 | formal review focused RED：伪造 Xvfb | 1 failed；已有伪造 authority 路径绕过门禁，且未连接 Display |
| 2026-07-25 | formal review focused GREEN | Xvfb forged/normal 2 passed；Shift 2 passed；scroll 1 passed；fresh import/lifecycle 3 passed |
| 2026-07-25 | formal review 最终 `tests/test_x11_keymap.py -v` | 48 passed，0.05s |
| 2026-07-25 | controlled `/proc` fixture focused RED | 2 failed；guard scanner 尚未接收受控 proc root/UID，测试以 `TypeError` 暴露依赖 |
| 2026-07-25 | controlled `/proc` fixture focused GREEN | 3 passed，0.03s；精确匹配、伪造拒绝和真实 `xvfb-run` 正向路径均通过 |
| 2026-07-25 | formal review 最终隔离 `tests/test_x11_integration.py -v` | 13 passed，0.21s；受控 proc fixture 覆盖精确绑定，真实 `xvfb-run` 验证默认 `/proc` 路径 |
| 2026-07-25 | formal review 最终 common `py_compile` | exit 0 |
| 2026-07-25 | formal review 最终 `pytest -m 'not x11' -v` | 98 passed / 14 deselected，0.36s |
| 2026-07-25 | formal review 最终 `xvfb-run -a ... pytest -v` | 111 passed / 1 deselected，0.60s；完整默认集合仅在隔离 Xvfb 中执行 |

## 阻塞项

- Orbbec Python wheel 当前加载其内置 SDK 2.8.6，而非设计指定的系统 SDK v2.9.3。实机采集已通过，但 ABI/库来源不符合设计；后续运行时诊断和依赖任务必须显式判定并解决，禁止通过隐式 `LD_LIBRARY_PATH` 改写或静默继续。
- 系统包或 udev 调整若需要 `sudo`，必须先请求用户批准。
