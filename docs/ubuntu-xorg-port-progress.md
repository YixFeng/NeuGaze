# Ubuntu 24.04 Xorg 移植进度

最后更新：2026-07-25

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
- 桌面生命周期：应用级所有权；pipeline 消费已初始化的 desktop，只在退出时 `release_all()`，不调用 `initialize()`/`close()`；Task 7 GUI 负责应用启动和关闭
- Pipeline cleanup：`quit_pipeline(primary_error=None)` 显式接收主异常；有主异常时保留同一异常对象和原 traceback，并用 notes 暴露 cleanup 失败；无主异常时聚合为 `BaseExceptionGroup`（成员全为 `Exception` 时由 Python 自动收窄为 `ExceptionGroup`）
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
- Task 8 兼容依赖基线：`mediapipe==0.10.14`、`opencv-python==4.11.0.86`、`opencv-contrib-python==4.11.0.86`、`numpy==1.26.4`
- Task 5 补齐既有声明依赖：`filterpy==1.4.5`、`onnxruntime==1.27.0`；`pip check` 报告无损坏依赖
- 仓库初始状态：`main` 与 `origin/main` 同步，开始设计时无本地改动

## 阶段状态

| 阶段 | 状态 | 验证 |
|---|---|---|
| 仓库与平台依赖摸底 | 完成 | 已记录 Win32、DirectShow、pywin32、keyboard、透明层和屏幕 API 调用 |
| 需求确认 | 完成 | 用户批准 Xorg、双平台、完整功能、非 root 运行和 Gemini 335 RGB |
| 设计评审 | 完成 | 用户分三部分批准设计 |
| 设计文档 | 完成 | 摄像头后端修订提交 `62dc98a`，用户已批准 |
| 实施计划 | 完成 | 8 个 TDD 任务已写入，提交 `6bf86ed`，待选择执行方式 |
| 实现 | 进行中（Task 1–6 完成） | Task 6 formal-review Critical/Important findings 已修复；未开始 Task 7 |
| 自动化验证 | 进行中 | Task 6 process 36 passed、focused regression 126 passed、完整 non-X11 192 passed / 18 deselected；正向 compositor 门禁受系统依赖阻塞 |
| Gemini 335 实机验收 | 未开始 | 需要连接设备和 Xorg 会话 |

## 任务进度

| 任务 | 状态 | 验证 |
|---|---|---|
| Task 1：测试基座与显式摄像头配置 | 完成 | 配置边界的 10 个测试通过 |
| Task 2：Fail-fast OpenCV/V4L2 与 Orbbec RGB 源 | 完成（有 SDK ABI 偏差） | 33 个 Task 1/2 单元测试通过；Gemini 335 读取 100 帧、关闭、重开后再读 1 帧通过 |
| Task 3：平台中立动作与显式桌面选择 | 完成 | selector/action 17 个测试通过（含 cleanup/lifecycle 并发回归）；common modules 编译通过；完整默认测试 50 passed / 1 deselected |
| Task 4：X11/XTest/XFixes 后端 | 完成（final safety re-review 修复） | 纯测试 49 passed；隔离 Xvfb 集成 14 passed；安全集合 99 passed / 15 deselected；Xvfb 完整默认集合 113 passed / 1 deselected |
| Task 5：生产 pipeline 接入摄像头与桌面边界 | 完成（redesign final re-review clean） | controller/runtime 57 passed；camera/action 回归 90 passed；隔离 Xvfb 完整默认集合 170 passed / 1 deselected |
| Task 6：受监督的 Xorg gaze overlay | 完成（formal-review fixes verified） | process 36 passed；focused regression 126 passed；non-X11 192 passed / 18 deselected；isolated negative 1 passed，positive compositor gate BLOCKED |

## 当前工作

Task 6 formal review 的四个根因已直接修复：所有 acquisition/transport/join/close 进入同一 cleanup boundary，保留原异常 identity/traceback 并逐项尝试清理；存活 child 依次 terminate、bounded join、kill、bounded join，仍存活或 close 失败时保留句柄并以 note 报告；child 仅在 Qt loop 和 Queue shutdown 成功后发送 `stopped`，parent join 后继续 drain control messages；timer 在无新点时仍推进非空 history。后续 re-review 的 compound-failure gap 也已修复：callback traceback 延迟到 child Queue cleanup 完成，若两者均失败则合并成一个 exact `("error", formatted_traceback)` tuple 且只发送一次。实现保持单模块直接控制流、Linux lazy Win32 route 与 Task 5 边界，未新增 manager/factory/base 抽象。正向 compositor 集成仍被 `xcompmgr` 与 `libxcb-cursor0` 缺失阻塞，未用 offscreen、备用实现或实时 `DISPLAY=:1` 掩盖。

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
| 2026-07-25 | final safety gate focused RED | 1 failed；不同 inode 的同名 `Xvfb` 在 UID/display/auth 匹配时被旧 basename 门禁接受 |
| 2026-07-25 | final safety gate focused GREEN | 受控 proc 3 passed；受控 inode、复制文件拒绝、伪造环境拒绝均通过；真实 `xvfb-run` 正向集合 4 passed |
| 2026-07-25 | underlying display close focused | 2 passed；release 失败和底层 close 失败均保留原异常与可重试 lifecycle；无需生产改动 |
| 2026-07-25 | final safety re-review 最终 `tests/test_x11_keymap.py -v` | 49 passed，0.05s |
| 2026-07-25 | final safety re-review 最终隔离 `tests/test_x11_integration.py -v` | 14 passed，0.21s |
| 2026-07-25 | final safety re-review common `py_compile` | exit 0 |
| 2026-07-25 | final safety re-review `pytest -m 'not x11' -v` | 99 passed / 15 deselected，0.37s |
| 2026-07-25 | final safety re-review `xvfb-run -a ... pytest -v` | 113 passed / 1 deselected，0.59s；完整默认集合仅在隔离 Xvfb 中执行 |

| 2026-07-25 | Task 5 `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py -v`（RED） | 0 collected / 2 collection errors；分别暴露 `win32api` 与 `win32gui` 顶层导入 |
| 2026-07-25 | Task 5 pipeline 首次 GREEN 尝试 | fail fast 暴露既有声明依赖缺失：先后为 `filterpy`、`onnxruntime`；未使用 stub/fallback |
| 2026-07-25 | 安装声明依赖并检查环境 | 安装 `filterpy==1.4.5`、`onnxruntime==1.27.0`；`pip check` 输出 `No broken requirements found.` |
| 2026-07-25 | Task 5 focused GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py -v`：19 passed，1.89s |
| 2026-07-25 | Task 5 要求的 camera/action 回归 GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`：52 passed，1.90s；无 unhandled thread warning |
| 2026-07-25 | Task 5 fail-fast ordering review RED/GREEN | 单测先以调用顺序 `inherited, raise_if_failed, decode` 失败；最小换序后 1 passed，1.84s |
| 2026-07-25 | Task 5 隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：132 passed / 1 deselected，2.44s；未连接实时 `DISPLAY=:1` |
| 2026-07-25 | Task 5 独立 review 后 focused RED | `tests/test_pipeline_runtime.py -v`：28 collected，13 passed / 15 failed；复现 idle action worker 不退出、action 错误无监督、join/release 竞态、calibration 吞 camera 错误、公共入口 camera 泄漏及 cleanup `BaseException` 覆盖主错误 |
| 2026-07-25 | Task 5 独立 review 修复后 runtime GREEN | `tests/test_pipeline_runtime.py -v`：28 passed，1.81s；无 unhandled thread warning |
| 2026-07-25 | Task 5 最终 camera/action 回归 GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`：65 passed，1.91s |
| 2026-07-25 | Task 5 最终隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：145 passed / 1 deselected，2.37s；未连接实时 `DISPLAY=:1` |
| 2026-07-25 | Task 5 formal review focused RED | controller/runtime 42 collected，31 passed / 11 failed；暴露 normal run 错误进入 terminal quit、controller stop 未 drain/重抛 late failure、隐式 gaze config Win32 import，以及 capture 双重 camera 来源 |
| 2026-07-25 | Task 5 formal review focused GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py -v`：42 passed，1.89s；覆盖同实例双次运行、action worker/wheel 复用、无陈旧 gaze、异常 identity/traceback 与 hotkey cleanup |
| 2026-07-25 | Task 5 formal review camera/action 回归 GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`：75 passed，1.83s |
| 2026-07-25 | Task 5 formal review 隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：155 passed / 1 deselected，2.38s；未连接实时 `DISPLAY=:1` |
| 2026-07-25 | Task 5 formal review compile/diff gate | 两个生产模块与两个测试模块 `py_compile` 通过；`git diff --check` exit 0 |
| 2026-07-25 | Task 5 second re-review focused RED | `tests/test_pipeline_runtime.py -v`：40 collected，32 passed / 8 failed；复现 calibration/demo cancellation 误走 reusable cleanup、terminal join 前未唤醒、final action 越过 normal boundary，以及 idle/token publication 无 condition handshake |
| 2026-07-25 | Task 5 second re-review focused GREEN | 移除把 demo ESC+Q 误标为 normal completion 的旧参数后，`tests/test_pipeline_runtime.py -v`：39 passed，1.88s；覆盖三种 terminal cancellation、final action 成功/失败 barrier、同 worker 双 run 和 exact error/traceback |
| 2026-07-25 | Task 5 second re-review camera/action 回归 GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`：80 passed，1.85s |
| 2026-07-25 | Task 5 second re-review 隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：160 passed / 1 deselected，2.44s；未连接实时 `DISPLAY=:1` |
| 2026-07-25 | Task 5 second re-review compile/diff gate | `pipeline.py` 与 `test_pipeline_runtime.py` 的 `py_compile` 通过；最终 focused repeat 39 passed，1.82s；`git diff --check` exit 0 |
| 2026-07-25 | Task 5 third review | persistent action worker/token protocol 与匿名 Tk thread 再次暴露生命周期竞态；旧完成状态撤销，用户批准 direct `RLock` + synchronous drain redesign |
| 2026-07-25 | Task 5 redesign focused RED | controller/runtime 55 collected，48 passed / 7 failed；暴露缺少同步 drain、旧 condition barrier、quit/start race、wheel 无显式 start，以及 persistent worker/token 残留 |
| 2026-07-25 | Task 5 redesign self-review RED/GREEN | wheel/controller 每 iteration 监督与 per-run wheel state：2 failed 后 2 passed；demo terminal quit 防止下一轮 evaluation：1 failed 后 1 passed；wheel worker 与 destroy-request 双失败时原错误优先：1 failed 后 1 passed |
| 2026-07-25 | Task 5 redesign focused GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py -v`：51 passed，1.91s |
| 2026-07-25 | Task 5 redesign camera/action 回归 GREEN | `tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_camera_sources.py -v`：84 passed，1.92s |
| 2026-07-25 | Task 5 redesign 隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：164 passed / 1 deselected，2.47s；未连接实时 `DISPLAY=:1` |

| 2026-07-25 | Task 5 redesign formal review | Needs fixes：Critical 为 Action failure 后迟到 wheel action 被 terminal drain 执行；Important 为首个 camera consumer 前 cleanup 可关闭资源；Minor source-string-test 建议按要求 deferred 到 final branch review |
| 2026-07-25 | formal-review fix Action RED | queued 路径 1 failed，1.85s：`executed == ['late']`；queued fix 后 direct 路径再 1 failed，1.90s：同样执行迟到 action |
| 2026-07-25 | formal-review fix Action GREEN | queued/final-boundary adjacent 3 passed，1.84s；统一 direct/queued Action boundary 与 hotkey 异常回归 4 passed，1.86s |
| 2026-07-25 | formal-review fix startup RED | evaluation、standalone calibration、demo evaluate/calibrate 的确定性交错 4 failed，1.90s；consumer 全部收到 cleanup 后的 `None` camera |
| 2026-07-25 | formal-review fix startup GREEN | 四条 first-consumer 交错、active demo external quit 与既有 start/quit race 共 6 passed，1.82s；terminal signal 在等待 RLock cleanup 前发布 |
| 2026-07-25 | formal-review fix focused/regression GREEN | controller/runtime 57 passed，1.94s；controller/runtime/keyboard/camera 90 passed，1.93s |
| 2026-07-25 | formal-review fix 隔离完整默认集合 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a ... -m pytest -v`：170 passed / 1 deselected，2.42s；未连接实时 `DISPLAY=:1` |
| 2026-07-25 | formal-review fix compile/diff/scope gate | `pipeline.py` 与 `test_pipeline_runtime.py` `py_compile` 通过；`git diff --check` exit 0；旧 worker/token 名称仅存在于 absence test；无 live Win32 import、无 `learn/` diff、无 `.orig/.rej` |
| 2026-07-25 | Task 5 final re-review | Spec compliant，Critical 0、Important 0，Task quality Approved；Minor source-string-test 建议留待 final branch review |

| 2026-07-25 | Task 6 依赖状态 | 已在非 root 环境 `/home/yixiao/miniconda3/envs/neugaze` 安装 `PySide6==6.11.1`；`xvfb-run` 可用；系统仍缺 `xcompmgr` 与 Qt xcb 所需 `libxcb-cursor0`。 |
| 2026-07-25 | Task 6 process RED | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest tests/test_gaze_overlay_process.py -v`：0 collected / 1 collection error；缺少 `gaze_overlay_x11`。 |
| 2026-07-25 | Task 6 X11 RED | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest tests/test_gaze_overlay_x11.py -v`：0 collected / 1 collection error；缺少 `gaze_overlay_x11`。 |
| 2026-07-25 | Task 6 focused GREEN | `tests/test_gaze_overlay_process.py -v`：16 passed，1.99s；覆盖 spawn、ready/error/death、latest point、stop ack/timeout、lazy selector、无 parent gaze thread。 |
| 2026-07-25 | Task 6 process lifetime self-review RED/GREEN | child error 后仍存活进程测试先 1 failed，最小 terminate/join 修复后 1 passed，1.98s。 |
| 2026-07-25 | Task 6 Xvfb 初次诊断 | Qt xcb 初始化 abort；`ldd libqxcb.so` 精确定位唯一缺失 `libxcb-cursor.so.0`，未切 offscreen/备用实现。 |
| 2026-07-25 | Task 6 Xvfb negative GREEN | 隔离 `xvfb-run -a ...::test_start_fails_visibly_when_x11_compositor_owner_is_missing -v`：1 passed，0.12s；真实 child traceback 显式返回 compositor gate 错误。 |
| 2026-07-25 | Task 6 X11 dependency-aware result | 隔离 `tests/test_gaze_overlay_x11.py -m x11 -v`：1 passed / 2 skipped，0.17s；仅 negative 通过，widget/positive 因真实系统依赖缺失而阻塞，未计为正向成功。 |
| 2026-07-25 | Task 6 focused regression GREEN | overlay/controller/runtime/keyboard/camera：106 passed，2.22s。 |
| 2026-07-25 | Task 6 完整 non-X11 GREEN | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest -m "not x11" -v`：172 passed / 18 deselected，2.40s。 |
| 2026-07-25 | Task 6 formal-review RED | 新增 15 个确定性 supervision 用例后 `tests/test_gaze_overlay_process.py -q`：16 passed / 15 failed；分别命中 partial acquisition、start/runtime/stop transport、join/close、terminate→kill、ack-without-exit、stopped→error、child shutdown 与 history tick。 |
| 2026-07-25 | Task 6 formal-review pre-commit RED/GREEN | EOF-aware clean stop 1 failed，callback error-send shutdown 1 failed；修复后两项与 stopped→error 合跑 3 passed，1.86s。EOF 仅在 ack + confirmed exit 后终止 drain，Qt shutdown 全部先尝试再传 error。 |
| 2026-07-25 | Task 6 formal-review process GREEN | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest tests/test_gaze_overlay_process.py -q`：35 passed，1.87s；原异常 identity 保留，所有清理操作均尝试，失败 close/live process 句柄保留。 |
| 2026-07-25 | Task 6 formal-review focused regression | overlay/controller/runtime/keyboard/camera：125 passed，2.09s。 |
| 2026-07-25 | Task 6 formal-review non-X11 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest -m 'not x11' -q`：191 passed / 18 deselected，2.29s。 |
| 2026-07-25 | Task 6 formal-review isolated X11 | missing-compositor gate 1 passed，0.12s；dependency-aware X11 file 1 passed / 2 skipped，0.16s；未连接实时 `DISPLAY=:1`。 |
| 2026-07-25 | Task 6 formal-review compile/scope | `py_compile`、`git diff --check`、`learn/` scope 与 `.orig/.rej` artifact gates 均 exit 0；系统仍缺 `xcompmgr` 与 `libxcb-cursor.so.0`，正向 compositor 门禁继续 BLOCKED。 |
| 2026-07-25 | Task 6 compound re-review RED/GREEN | callback + Queue-close compound 与 retained send-failure 聚焦 RED：2 failed；最小 deferred traceback 修复后，compound/adjacent 4 passed，1.96s，exactly one error tuple 同时包含两段 traceback。 |
| 2026-07-25 | Task 6 compound re-review regression | process 36 passed，1.93s；overlay/controller/runtime/keyboard/camera 126 passed，2.08s；non-X11 192 passed / 18 deselected，2.32s。 |
| 2026-07-25 | Task 6 compound re-review X11/static | isolated negative 1 passed，0.12s；dependency-aware 1 passed / 2 skipped，0.16s；`py_compile`、diff/scope/artifact gates exit 0；模块 534 行。 |


## 阻塞项

- Orbbec Python wheel 当前加载其内置 SDK 2.8.6，而非设计指定的系统 SDK v2.9.3。实机采集已通过，但 ABI/库来源不符合设计；后续运行时诊断和依赖任务必须显式判定并解决，禁止通过隐式 `LD_LIBRARY_PATH` 改写或静默继续。
- Task 6 compositor 正向门禁 BLOCKED：缺少系统包 `xcompmgr` 和 `libxcb-cursor0`。依赖就绪后必须原样运行 `xvfb-run -a sh -c 'xcompmgr -a & /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_overlay_x11.py -m x11 -v'`，不得用 offscreen 或 live `DISPLAY=:1` 替代。
- 系统包或 udev 调整若需要 `sudo`，必须先请求用户批准。
