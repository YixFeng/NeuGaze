# Ubuntu 24.04 Xorg 移植进度

最后更新：2026-07-27

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
- Task 8 审查基线（已批准 Task 1–7）：`f632509`
- Task 8 初始范围提交：`625061e`（`docs: add Ubuntu Xorg setup and verification`）
- Task 8 评审修复提交：`260680e`（`fix: harden Ubuntu runtime diagnostics`）

## 已确认决策

- 目标系统：Ubuntu 24.04 x86-64
- 桌面会话：Xorg
- Windows：保留现有支持
- 功能范围：GUI、预览、校准、评估、凝视鼠标、完整键鼠映射、轮盘、透明凝视层
- Ubuntu 摄像头后端：明确选择 `orbbec` 或 `opencv`，不自动切换
- 当前默认摄像头：Orbbec Gemini 335
- 摄像头数据：仅 RGB，`1280x720 @ 30 FPS`
- Ubuntu 摄像头 API：`pyorbbecsdk2==2.1.1` + wheel 内置 SDK 2.8.6（2026-07-26 用户批准选项 A）
- Orbbec Python 原生库：`ldd` 必须解析到导入的 `pyorbbecsdk` 包内 `libOrbbecSDK.so.2`；系统 SDK 2.9.3 仅作信息发现
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
- Orbbec SDK 系统库：`/usr/local/lib/libOrbbecSDK.so.2.9.3`（保持不变，仅作信息发现，不是 Python 运行前置）
- Orbbec SDK 安装目录：`/opt/OrbbecSDK_v2.9.3`（保持不变，仅作信息发现）
- Python Orbbec 绑定：`pyorbbecsdk2==2.1.1`（包版本 2.1.1，SDK 版本 API 报告 2.8.6）
- Task 8 兼容依赖基线：`mediapipe==0.10.14`、仅 `opencv-contrib-python==4.11.0.86`、`numpy==1.26.4`；禁止同时安装拥有相同 `cv2` 文件的 `opencv-python`
- Task 5 补齐既有声明依赖：`filterpy==1.4.5`、`onnxruntime==1.27.0`；`pyorbbecsdk2` 与 `ncnn` 的上游 metadata 仍无条件要求分发名 `opencv-python`，见 Task 8 显式例外
- 仓库初始状态：`main` 与 `origin/main` 同步，开始设计时无本地改动

## 阶段状态

| 阶段 | 状态 | 验证 |
|---|---|---|
| 仓库与平台依赖摸底 | 完成 | 已记录 Win32、DirectShow、pywin32、keyboard、透明层和屏幕 API 调用 |
| 需求确认 | 完成 | 用户批准 Xorg、双平台、完整功能、非 root 运行和 Gemini 335 RGB |
| 设计评审 | 完成 | 用户分三部分批准设计 |
| 设计文档 | 完成 | 摄像头后端修订提交 `62dc98a`，用户已批准 |
| 实施计划 | 完成 | 8 个 TDD 任务已写入，提交 `6bf86ed`，待选择执行方式 |
| 实现 | Task 1–8 自动化范围完成，人工验收待执行 | 2026-07-26 用户批准 ABI 选项 A；诊断强制 wheel 分发 2.1.1、内置 SDK 2.8.6 与包内原生库，无回退 |
| 自动化验证 | 完成（fresh HEAD） | camera focused 45 passed；non-X11 392 passed / 23 deselected；隔离 Xvfb 无/有 compositor 各 21 passed / 1 expected skip / 393 deselected；live diagnostic 12/12 PASS；install check 14/14 PASS；编译与静态门禁通过 |
| Gemini 335 实机验收 | 部分完成 | 当前用户 Xorg 已验证；Orbbec 100 帧、关闭、重开、一帧通过；GUI、九点校准、输入、物理断开仍需人工验收 |

## 任务进度

| 任务 | 状态 | 验证 |
|---|---|---|
| Task 1：测试基座与显式摄像头配置 | 完成 | 配置边界的 10 个测试通过 |
| Task 2：Fail-fast OpenCV/V4L2 与 Orbbec RGB 源 | 完成 | 33 个 Task 1/2 单元测试通过；Gemini 335 读取 100 帧、关闭、重开后再读 1 帧通过 |
| Task 3：平台中立动作与显式桌面选择 | 完成 | selector/action 17 个测试通过（含 cleanup/lifecycle 并发回归）；common modules 编译通过；完整默认测试 50 passed / 1 deselected |
| Task 4：X11/XTest/XFixes 后端 | 完成（final safety re-review 修复） | 纯测试 49 passed；隔离 Xvfb 集成 14 passed；安全集合 99 passed / 15 deselected；Xvfb 完整默认集合 113 passed / 1 deselected |
| Task 5：生产 pipeline 接入摄像头与桌面边界 | 完成（redesign final re-review clean） | controller/runtime 57 passed；camera/action 回归 90 passed；隔离 Xvfb 完整默认集合 170 passed / 1 deselected |
| Task 6：受监督的 Xorg gaze overlay | 完成（external gate resolved） | process 36 passed；focused regression 126 passed；non-X11 192 passed / 18 deselected；isolated negative 1 passed；positive compositor 2 passed / 1 skipped；compositor 完整集合 208 passed / 1 skipped / 1 deselected |
| Task 7：GUI 摄像头后端、预览与配置 roundtrip | 完成（final re-review fixes verified） | GUI/camera 56 passed；Task 5/6 ownership/overlay regression 149 passed；offscreen non-X11 215 passed / 18 deselected；static/scope/import gates 通过 |
| Task 8：Ubuntu 依赖、诊断、文档与全量验证 | 自动化实现完成，人工验收待执行 | formal review fix focused 55 passed、实时诊断 11/11 passed、non-X11 270 passed / 18 deselected、两组 X11 各 16 passed / 1 skipped、Gemini 335 hardware 1 passed；`pip check` 两条 metadata 例外未记为通过 |

## Ubuntu robot terminal actions 阶段

本阶段在 `ubuntu-xorg-port` 上把 Ubuntu 表情和凝视轮盘收束为可审计的终端动作行；不接入 SONIC，也不把真人验收写成已完成。设计证据保留为 `7a8f897`（设计）、`3998fe6`（中文设计）和 `4a022c8`（实施计划）。实施提交依次为 `18c8880`（动作合同）、`441fac6`（固定 action ID）、`b6a776e`（Ubuntu 表情路由）、`d0d0aa6`（凝视选择四向轮盘）、`14d6f07`（隔离 robot gaze 与桌面输入）及 `49aa923`（轮盘动作链覆盖修复）。

| 项目 | 状态 | 本阶段新证据（2026-07-27，HEAD `49aa923`） |
|---|---|---|
| focused 自动化 | 通过 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py tests/test_pipeline_runtime.py tests/test_gaze_mouse_controller.py tests/test_keyboard_actions.py tests/test_desktop_selection.py tests/test_config_gui_camera.py -v`：160 passed，8.08s；无 warning、无 unhandled thread exception。 |
| non-X11 全量自动化 | 通过 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m 'not x11' -v`：439 passed / 23 deselected，8.81s。23 个 deselected 是 marker 选择结果，不记为通过。 |
| Xvfb，无 compositor | 通过（含 expected skip） | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m x11 -v`：21 passed / 1 skipped / 440 deselected，2.75s；skip 为 `test_overlay_handshake_update_and_synchronous_stop_with_compositor`，原因是正向集成需要 `xcompmgr`。440 个 deselected 不记为通过。 |
| Xvfb，有 compositor | 通过（含 expected skip） | `xvfb-run -a sh -c 'xcompmgr -a & PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m x11 -v'`：21 passed / 1 skipped / 440 deselected，2.52s；skip 为 `test_start_fails_visibly_when_x11_compositor_owner_is_missing`，原因是它需要没有 compositor 的隔离显示。child stderr 另有 `X connection to :102 broken (explicit kill or server shutdown).`，发生在 Xvfb 关闭时；pytest exit 0。440 个 deselected 不记为通过。 |
| 真人验收 | 未执行 | 仅新增 `docs/ubuntu-robot-terminal-acceptance.md`；中立 2 分钟、三个直接表情各 5 次、四方向各 5 次、取消、无键鼠副作用和退出资源检查均待真实 Xorg/Gemini 335 执行。 |
| 编译与范围门禁 | 通过 | `/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile my_model_arch/cpu_fast/robot_actions.py my_model_arch/cpu_fast/eye_gaze_mouse_control.py my_model_arch/cpu_fast/pipeline.py config_gui_cpu.py tests/test_robot_actions.py tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_config_gui_camera.py`：实际 exit 0；同轮 `git diff --check`、临时工件检查与 `git diff --cached --check` 均 exit 0。 |
| SONIC 接入 | 未开始 | 当前只打印 Terminal 行；未新增 SONIC、ZMQ 或机器人依赖。 |

## 当前工作

Task 7 将 GUI 摄像头链路改为显式平台配置：Linux 后端选择直接调用 `list_cameras` / `open_camera`，Orbbec model/serial 与 V4L2 device label 的 backend/device ID 保存在 combo item data；preview 直接以 ndarray 的 BGR 通道、真实宽高和 stride 构造 `QImage`。backend 切换先在阻断信号时清空并禁用 device IDs，再尝试关闭旧 preview；close 失败保留原 camera/异常且不枚举、不打开、不重试。calibration/evaluation handoff 先关闭 GUI preview；确认新摄像头会终止持有旧 camera config 的 pipeline。camera enumeration/open/read、pipeline 初始化、calibration preview restart 和 desktop shutdown 的原异常 identity/traceback 可见且无 retry/fallback。YAML 保存直接在各层原 mapping 的深拷贝上覆盖 UI 所有字段，完整 hydration nullable path、screen size、颜色与 gaze bias；expression conditions 统一通过 `ExpressionRow.set_condition()` hydration，每个 row 自持 deep-copied origin mapping，删除/重排不会把未知 metadata 转移给相邻条件。保存保留各 section/expression condition/priority/key item 的未知嵌套键、未触碰值及 `camera_backend["win32"] == "opencv"`。desktop 仅由 `run_gui` 在应用启动/退出时 initialize/close，pipeline 所有权未改；GUI 顶层 `keyboard`/DirectShow 路径已移除。未修改 `learn/`；Task 8 状态见下段。

Task 8 新增完全锁定的 `requirements-ubuntu.txt`，保留 Windows `requirements.txt` 不变，并排除 `pywin32`、`keyboard`、`pyautogui` 与 CUDA wheel。诊断逐项检查 Python、Linux、Xorg、DISPLAY、XTest、XFixes、按需 compositor、配置、模型文件、Orbbec 包/SDK/`ldd` 库来源和明确选择的摄像头；所有失败聚合并保留 traceback，无安装、重试、环境变量改写、udev 修改或后端回退。第三方 Orbbec 枚举会在当前目录写 `Log/OrbbecSDK.log.txt`，因此只把该枚举放进临时工作目录的子进程；结构化结果、stdout、stderr 和失败状态返回父进程，临时目录自动清理，实际诊断不再污染仓库。2026-07-26 用户批准选项 A 后，权威合同为 `pyorbbecsdk2==2.1.1`、SDK API 2.8.6、`ldd` 解析到导入包内 `libOrbbecSDK.so.2`；系统 2.9.3 只打印为信息，不参与成功判定。

同日 formal review 修复轮次中，用户明确批准 OpenCV 方案 B：Ubuntu manifest 与环境只保留 `opencv-contrib-python==4.11.0.86`，不安装 alias/dummy、不改写 dist-info，也不恢复冲突 wheel。由于精确 pin 的上游 `pyorbbecsdk2==2.1.1` 和 `ncnn==1.0.20260526` 都无条件声明 `Requires-Dist: opencv-python`，`pip check` 必须如实以 1 退出并报告这两条分发名冲突；这不是通过项，也不被过滤。例外边界只限 metadata：实际门禁仍验证 contrib-only metadata、`cv2==4.11.0`、MediaPipe/Orbbec 导入、11 项只读诊断与 Gemini 335 实机读取。

当前获批准的 `pip check` exit 1 原文是：

```text
pyorbbecsdk2 2.1.1 requires opencv-python, which is not installed.
ncnn 1.0.20260526 requires opencv-python, which is not installed.
```


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
| 2026-07-25 | 安装声明依赖并检查环境 | 安装 `filterpy==1.4.5`、`onnxruntime==1.27.0`；`pip check` 当时输出 `No broken requirements found.`。这是 contrib-only 方案 B 前双 wheel 环境的已废止历史证据，不是当前 gate。 |
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
| 2026-07-26 | Task 6 positive compositor gate | 原样运行 `xvfb-run -a sh -c 'xcompmgr -a & ... tests/test_gaze_overlay_x11.py -m x11 -v'`：exit 0，2 passed / 1 skipped，0.32s；skip 仅为需要无 compositor 的 negative 用例；无 warning，child stderr 仅为 Xvfb 关闭连接提示。 |
| 2026-07-26 | Task 6 isolated compositor full suite | 原样运行 `xvfb-run -a sh -c 'xcompmgr -a & ... -m pytest -v'`：exit 0，208 passed / 1 skipped / 1 deselected，2.77s；无 warning，child stderr 仅为 Xvfb 关闭连接提示；无残留 Xvfb/xcompmgr/pytest 进程，git status/diff gates clean。 |
| 2026-07-26 | Task 7 GUI RED | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen .../python -m pytest tests/test_config_gui_camera.py -v`：exit 2，0 collected / 1 collection error；顶层 `import keyboard` 触发 `ModuleNotFoundError`。 |
| 2026-07-26 | Task 7 首次 focused GREEN | offscreen GUI 15 passed，2.65s；backend/default/order/item-data、direct BGR preview、visible traceback、roundtrip、hotkey 与 desktop lifecycle 均通过。 |
| 2026-07-26 | Task 7 compound lifecycle RED/GREEN | camera read + cleanup 与 event-loop + desktop-close compound 用例先 2 failed，最小修复后 2 passed，0.39s；保留主异常并把 cleanup failure 放入同一 visible traceback/note。 |
| 2026-07-26 | Task 7 stale pipeline RED/GREEN | 更换 camera 后旧 pipeline retirement 用例先 1 failed，最小修复后 1 passed，0.31s。 |
| 2026-07-26 | Task 7 independent review RED/GREEN | no-retry close 与 stale device enumeration 两项 Important 用例先 2 failed；拆分 close/open boundary 并在 enumeration 前清空/禁用 device combo 后 2 passed，0.44s；Critical 0。 |
| 2026-07-26 | Task 7 最终 camera regression | `tests/test_config_gui_camera.py tests/test_camera_config.py tests/test_camera_sources.py -v`：51 passed，4.69s；无 Qt warning。 |
| 2026-07-26 | Task 7 Task 5/6 focused regression | GUI/overlay/controller/runtime/keyboard/camera：144 passed，7.14s。 |
| 2026-07-26 | Task 7 完整 offscreen non-X11 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen .../python -m pytest -m 'not x11' -q`：210 passed / 18 deselected，7.37s；未连接实时 `DISPLAY=:1`。 |
| 2026-07-26 | Task 7 static/scope/import gates | `py_compile`、`git diff --check`、Linux import isolation、无 GUI `keyboard`/`self.cap`/DirectShow/cv2、无 `learn/` diff、无 `.orig/.rej` 均 exit 0。 |
| 2026-07-26 | Task 7 formal-review RED | 新增 lossless YAML roundtrip、calibration restart 传播、backend close-failure 失效顺序三项确定性用例；exact focused command：3 failed，0.54s。分别暴露 nullable path 为 `"None"`/特殊 widgets 未 hydration 且 section 重建丢键、callback 宽泛捕获吞错、旧 device combo 在 close 前仍为 enabled/stale。 |
| 2026-07-26 | Task 7 formal-review focused GREEN | direct deep-copy merge、完整 widget hydration、移除 callback 吞错边界、close 前 signal-blocked invalidate 后 exact focused command：3 passed，0.55s；增强的 blocked-signal/exactly-once-format 两项：2 passed，0.41s。 |
| 2026-07-26 | Task 7 formal-review camera regression | `tests/test_config_gui_camera.py tests/test_camera_config.py tests/test_camera_sources.py -q`：54 passed，5.35s；无 Qt warning。 |
| 2026-07-26 | Task 7 formal-review Task 5/6 regression | GUI/overlay/controller/runtime/keyboard/camera：147 passed，7.63s。 |
| 2026-07-26 | Task 7 formal-review non-X11 | 完整 offscreen：213 passed / 18 deselected，7.86s；未连接实时 `DISPLAY=:1`。 |
| 2026-07-26 | Task 7 formal-review static/scope/import | `py_compile`、`git diff --check`、Linux no-Win32 live import、GUI 禁用引用、`learn/`、artifact、changed-file scope 均 exit 0。 |
| 2026-07-26 | Task 7 expression final re-review RED | exact focused command 在 production edit 前运行：2 failed，0.47s。untouched BETWEEN 的 `min/max=.25/.75` 实际为 `0/0`，DIFF fixture 覆盖 `compare_to=jawRight`；删除首 condition 后 expression-config equality 失败，暴露按 layout index 转移 unknown metadata。 |
| 2026-07-26 | Task 7 expression final re-review GREEN | setup 统一调用 `ExpressionRow.set_condition()`，row 自持 deep-copied origin，serialization 直接合并该 origin 与 UI-owned keys；同一 exact command：2 passed，0.46s。 |
| 2026-07-26 | Task 7 expression final regression | GUI/camera 56 passed，3.28s；Task 5/6 149 passed，5.53s；完整 offscreen non-X11 215 passed / 18 deselected，5.79s；无 warning。 |
| 2026-07-26 | Task 7 expression final static/bookkeeping | `py_compile`、diff/import/forbidden refs/learn/artifact/scope 均 exit 0；reviewed final head：`config_gui_cpu.py` 2553 行，GUI test 907 行 / 23 collected。 |

| 2026-07-26 | Task 8 diagnostic RED | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest tests/test_ubuntu_runtime_check.py -v`：exit 2，0 collected / 1 collection error；`ModuleNotFoundError: No module named scripts`。 |
| 2026-07-26 | Task 8 diagnostic 首次 GREEN | 同一文件 14 passed，0.02s；覆盖成功、聚合 traceback、错误 Python、Wayland、无 DISPLAY、XTest/XFixes、compositor、模型、V4L2 选择与 Orbbec ABI。 |
| 2026-07-26 | 初次实时诊断 | 当前用户 `DISPLAY=:1` 上 10 PASS / 1 FAIL，exit 1；唯一失败为 `pyorbbecsdk2=2.1.1`、SDK 2.8.6、wheel 内 `libOrbbecSDK.so.2`，而设计期望 `/usr/local/lib/libOrbbecSDK.so.2.9.3`；Gemini 335 型号、序列号 `CP0E85300058` 与 1 台设备检查通过。 |
| 2026-07-26 | Orbbec 诊断副作用定位 | Context/设备枚举可复现生成仓库 `Log/OrbbecSDK.log.txt`；日志来自第三方 SDK device watcher/device creation，不是任务源文件，已移除。 |
| 2026-07-26 | Orbbec 临时目录隔离 RED/GREEN | focused RED 1 failed：缺少 `query_orbbec_devices`；最小子进程/临时 cwd 修复后 focused 1 passed，完整 diagnostic 15 passed，0.02s。 |
| 2026-07-26 | 实时诊断无污染复验 | 仍为 10 PASS / 1 ABI FAIL；随后 `git status --short` 仅列预期 Task 8 文件，`find . -maxdepth 1 -name Log` 无输出，无手工清理。 |
| 2026-07-26 | Ubuntu requirements 与环境比对 | `pip check` 当时为 `No broken requirements found.`；16 个已安装锁定项全部精确匹配，显式要求的 `torchaudio==2.6.0+cpu` 当前未安装；未安装/升级任何包；Windows requirements SHA-256 保持 `6cc7a8fd64df6ee4dd1d70b1d11438108605320fe5519188c8d8e700b539b916`。这是 contrib-only 方案 B 前双 wheel 环境的已废止历史证据，不是当前 gate。 |
| 2026-07-26 | 当前会话所有权 | `DISPLAY=:1`、`XDG_SESSION_TYPE=x11`、Xauthority `/run/user/1000/gdm/Xauthority`；Xorg PID 769526 与 GNOME Shell 均由 uid 1000 `yixiao` 所有。 |
| 2026-07-26 | Gemini 335 显式硬件命令 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest tests/test_orbbec_hardware.py --run-orbbec -v`：1 passed，8.48s；读取 100 帧、关闭、重开并再读 1 帧。 |
| 2026-07-26 | OpenCV/V4L2 显式源检查 | 只调用 `open_camera(CameraConfig("opencv", 0, 1280, 720, 30), "linux")`；`/dev/video0` 打开、返回 `(720, 1280, 3) uint8 C-contiguous` 一帧并关闭，exit 0；未调用 Orbbec 后端或回退。当前 `/dev/video0`–`/dev/video7` 均标识为 Gemini 335，没有独立普通 USB 摄像头证据。 |
| 2026-07-26 | Task 8 non-hardware/non-X11 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .../python -m pytest -m "not hardware and not x11" -v`：最终 fresh 230 passed / 18 deselected，5.76s。 |
| 2026-07-26 | Task 8 exact isolated X11 | `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a .../python -m pytest -m x11 -v`：最终 fresh 16 passed / 1 skipped / 231 deselected，2.41s；通过无 compositor fail-fast，positive compositor 用例按条件跳过；未连接实时 `DISPLAY=:1`。 |
| 2026-07-26 | Task 8 isolated positive compositor | 隔离 `xvfb-run` 内启动 `xcompmgr -a` 后运行完整 `-m x11`：最终 fresh 16 passed / 1 skipped / 231 deselected，2.35s；正向 overlay 通过，缺 compositor negative 按条件跳过；未连接实时 `DISPLAY=:1`。 |
| 2026-07-26 | Task 8 compile | `.../python -m py_compile config_gui_cpu.py my_model_arch/cpu_fast/*.py my_model_arch/cpu_fast/desktop/*.py scripts/check_ubuntu_runtime.py`：exit 0。 |
| 2026-07-26 | Task 8 最终 fresh verification | diagnostic unit 15 passed；non-hardware/non-X11 230 passed / 18 deselected；isolated X11 negative 16 passed / 1 skipped / 231 deselected；isolated X11 positive 16 passed / 1 skipped / 231 deselected；compile exit 0；实时 diagnostic 10 PASS / 1 ABI FAIL；Gemini hardware 1 passed，8.42s。硬件测试本身再次生成 7467-byte `Log/OrbbecSDK.log.txt`，记录后删除；诊断命令仍不生成该文件。 |
| 2026-07-26 | Task 8 正式评审 | 审查 `f632509..625061e`：无 critical；6 项 important 要求补强 Ubuntu/架构边界、完整摄像头配置与设备真实性、`ldd not found`、复合清理异常、build wiring 和硬件测试开发依赖说明；ABI/人工验收/缺少 torchaudio 仍是诚实阻塞项。 |
| 2026-07-26 | Task 8 review RED | diagnostic focused 收集 31 项：14 failed / 17 passed，精确暴露上述代码缺口；未改 ABI 预期。 |
| 2026-07-26 | Task 8 review focused GREEN | diagnostic focused 32 passed，0.02s；原始子进程失败及 stdout/stderr 保留，清理失败只作为原错误 note，V4L2 字符设备/读写权限和 Gemini 335/profile 显式验证。 |
| 2026-07-26 | SDK 型号表示 RED/GREEN | 首次 review 后实时诊断额外暴露 `Orbbec Gemini 335` 与过窄精确值 `Gemini 335` 的假阴性：9 PASS / 2 FAIL；focused RED 1 failed。仅允许两个已知官方表示后 focused 32 passed，其他型号仍 fail fast。 |
| 2026-07-26 | Task 8 review final gates | non-hardware/non-X11 247 passed / 18 deselected，5.85s；isolated X11 negative 16 passed / 1 skipped / 248 deselected，2.43s；positive compositor 16 passed / 1 skipped / 248 deselected，2.34s；validated glob compile exit 0。 |
| 2026-07-26 | Task 8 review 最终实时诊断 | 10 PASS / 1 ABI FAIL，exit 1；Ubuntu 24.04 x86_64、完整 1280x720@30 配置和 `Orbbec Gemini 335`/序列号通过，唯一失败仍为批准的 2.9.3/system authority 与 wheel 2.8.6/内置库偏差；仓库无 `Log/`。 |
| 2026-07-26 | Task 8 正式复审 | Critical 0、Important 0；唯一 Minor 为进度表 31/32 计数，已在本行前校正；ABI constants 和无 fallback 策略保持不变。 |

## Option A 批准后验证

上方截至 `Task 8 正式复审` 的 ABI failure/NEEDS_CONTEXT 行均为用户批准前历史证据，原样保留，不代表当前合同。2026-07-26 批准后的新增证据如下：

| 日期 | 命令或检查 | 结果 |
|---|---|---|
| 2026-07-26 | Option A 精确 RED | production 保持 `260680e` 不变，仅修改测试；单测 1 failed，0.03s，原因为旧合同仍报 `SDK version expected 2.9.3, got 2.8.6`。 |
| 2026-07-26 | Option A focused RED | 6 selected：5 failed / 1 passed，0.05s；覆盖 bundled success、system informational、system path failure、其他 SDK failure、imported-package data flow 与 binding pin。 |
| 2026-07-26 | Option A focused GREEN | 6 passed / 30 deselected，0.03s；无环境、系统库或 fallback 修改。 |
| 2026-07-26 | Option A diagnostic unit GREEN | 36 passed，0.03s。 |
| 2026-07-26 | Option A 首次实时诊断 GREEN | 当前用户 `DISPLAY=:1` 上 11/11 checks passed，exit 0；打印 `pyorbbecsdk2=2.1.1`、SDK 2.8.6、包内 `libOrbbecSDK.so.2` 及 informational `/usr/local/lib/libOrbbecSDK.so.2.9.3`；随后仓库无 `Log/`，status 仅含预期源文件。 |
| 2026-07-26 | 缺失 pin 安装 | 先确认 `torchaudio` 未安装；随后仅执行 CPU index 的 `torchaudio==2.6.0+cpu --no-deps` 非 root 安装，成功且 import 报告 2.6.0+cpu，未升级其他包。 |
| 2026-07-26 | Ubuntu pins 与环境完整性 | `requirements-ubuntu.txt` 当时的 17 个 exact pins 全部逐项匹配；`pip check` 当时为 `No broken requirements found.`。这是 contrib-only 方案 B 前双 wheel 环境的已废止历史证据，不是当前 gate。 |
| 2026-07-26 | Option A non-hardware/non-X11 | 269 collected；251 passed / 18 deselected，6.21s。 |
| 2026-07-26 | Option A isolated X11 | 无 compositor：16 passed / 1 skipped / 252 deselected，2.72s；`xcompmgr -a`：16 passed / 1 skipped / 252 deselected，2.64s；均未连接实时 `DISPLAY=:1`。 |
| 2026-07-26 | Option A Gemini 335 hardware | 1 passed，8.40s；读取 100 帧、关闭、重开并再读 1 帧。第三方 SDK 生成 7,471-byte `Log/OrbbecSDK.log.txt`，记录后精确删除文件与空目录。 |
| 2026-07-26 | Option A compile | validated plan glob 加 `tests/test_ubuntu_runtime_check.py` 的 `py_compile` exit 0。 |
| 2026-07-26 | Option A final unit/live | diagnostic unit 36 passed，0.03s；随后实时 `DISPLAY=:1 --require-overlay` 再次 11/11 passed、exit 0，仓库仍无 `Log/`。 |
| 2026-07-26 | Option A final static/scope | 仅 7 个批准的 resolution 文件；`git diff --check`、`learn/`、stale mandate、env rewrite、forbidden dependency、artifact gates 均通过。Windows `requirements.txt` SHA-256 保持 `6cc7a8fd64df6ee4dd1d70b1d11438108605320fe5519188c8d8e700b539b916`；system 2.9.3 文件仍为 root-owned 13,254,456 bytes、mode 644。 |

## Task 8 实机会话验收

1. **实时诊断：批准后已通过。** 当前用户 `DISPLAY=:1` 上 11/11 checks passed，exit 0；同时打印权威 bundled 2.8.6 证据与 informational system 2.9.3 证据。
2. **Orbbec 硬件：已执行。** 程序化型号/序列号检查与 100 帧、关闭、重开、一帧通过；这不等同于 GUI 人工预览确认。
3. **GUI Gemini 335 label/serial 与 100 帧预览：未执行人工 GUI 验收。** 仍需启动 GUI，确认显示 `Orbbec Gemini 335 CP0E85300058`，预览持续至少 100 帧且关闭/重开正常。
4. **OpenCV/V4L2：部分执行。** 显式 V4L2 `/dev/video0` 单帧路径通过且无 Orbbec SDK 回退；GUI 后端切换未人工确认，当前也没有独立普通 USB 摄像头，只有 Gemini 335 暴露的 V4L2 节点。
5. **九点校准：未执行。** 需要完成全部九点并确认保存的回归模型可加载。
6. **输入与 overlay：未执行实时人工验收。** 自动化只在隔离 Xvfb 验证。人工需逐项确认：凝视绝对/相对移动；左/右/中/X1/X2；滚动；按下/保持/释放；组合键；安全释放；表情映射；轮盘选择；透明、置顶、点击穿透、不抢焦点；ESC+Q 停止 evaluation、随后正常关闭 GUI 后无残留按键、按钮、overlay、摄像头或进程。
7. **物理断开 Gemini 335：未执行。** 预览中拔出设备后必须显示原始 SDK 错误并终止当前操作，不得返回空帧、重试或切 V4L2。
8. **非 root：已确认本次 Task 8 命令。** 所有记录的诊断、测试、摄像头与编译命令均由 uid 1000 执行且未使用 `sudo`；这不代替后续人工会话对命令历史的复核。

## Orbbec ABI 决策（已解决）

2026-07-26 用户明确批准选项 A。权威运行时合同是：

- Python 分发必须为 `pyorbbecsdk2==2.1.1`；
- `pyorbbecsdk.get_version()` 必须返回 `2.8.6`；
- 导入扩展经 `ldd` 解析的 `libOrbbecSDK.so.2` 必须位于该 `pyorbbecsdk` 包目录；
- 解析到 `/usr/local/lib/libOrbbecSDK.so.2.9.3`、其他路径/版本或其他 SDK 版本必须失败；
- 系统 SDK 2.9.3 保持不变，只作为 informational discovery 打印，不是 Python 运行前置条件。

ELF 证据：扩展 `NEEDED` 为 `libOrbbecSDK.so.2` 且 `RUNPATH=$ORIGIN`，当前正常解析到导入包内库。禁止 `LD_LIBRARY_PATH`、`LD_PRELOAD`、环境改写、替换 wheel/系统库、修改软链接、自动重试、构建或后端回退。


## 阻塞项

- 自动化与 ABI authority 已无阻塞；GUI 视觉预览、九点校准、实时输入/overlay、ESC+Q 停止 evaluation 后正常关闭 GUI 的 cleanup 与物理断开仍需人工验收，未标记通过。
- 后续系统包或 udev 调整若需要 `sudo`，必须先请求用户批准。


## 最终全分支 review 修复波次（第 1 段）

| 日期 | 证据 | 结果 |
|---|---|---|
| 2026-07-26 | A–F 初始行为 RED | 26 failed / 1 passed；生产未修改时精确暴露 Orbbec、ownership、terminal queue、bool、action 与 Win32 缺口。 |
| 2026-07-26 | scoped review RED/GREEN | reviewer：Critical 0、Important 2、Minor 1；NONE routing 3 failed / 1 passed，Orbbec enumeration 3 failed；全部修复后 camera/pipeline 96 passed。 |
| 2026-07-26 | 最终 focused / non-X11 | domain focused 152 passed，5.88s；完整 non-X11 301 passed / 18 deselected，6.22s。 |
| 2026-07-26 | Windows 验收边界 | fake route 仅证明 DirectShow 与 GetDC/GetDeviceCaps/ReleaseDC 控制流；Windows 实机摄像头及 100%/125%/150% DPI 对齐仍需人工验收，未标记通过。 |


## 最终全分支 review 修复波次（第 2–3 段）

| 提交 | 内容 |
|---|---|
| `84a68dc` | 采用 wheel bundled Orbbec SDK 权威运行时 |
| `9217ae8` | 收紧 Ubuntu runtime 与 OpenCV 安装合同 |
| `0c485eb` | 将 Orbbec 导入绑定到同一 Distribution provenance |
| `06b7123` | 修复 camera cleanup、terminal action 与 Windows 边界 |
| `ca0c631` | XI2 初始化、五鼠标键状态与 owned-release |
| `4950cce` | 每次状态查询重新验证唯一 master pointer topology |
| `95d60fc` | 新增只读 Ubuntu 安装验证与最终第 3 段收口 |

第 2 段最终隔离 live runtime diagnostic 为 **12/12 PASS**，包括独立
XInput/XI2 检查。第 3 段新增的安装检查器只读报告系统包、命令、Conda 与
udev 状态；任何 apt 或 udev 修复仍必须先取得用户批准，日常 runtime 不使用
sudo。已批准的 pip metadata exception 保持不变：只允许
`pyorbbecsdk2==2.1.1` 与 `ncnn==1.0.20260526` 报告缺少分发名
`opencv-python`，不得安装 alias/dummy、修改 metadata 或恢复冲突 wheel。

Windows 实机摄像头、100%/125%/150% DPI 与完整 GUI 链路仍是 manual
acceptance boundary；Linux fake route 不把这些人工项目标记为通过。

第 3 段最终验证（2026-07-26）：

| 门禁 | 结果 |
|---|---|
| 第 3 段 focused | 202 passed，4.39s |
| 完整 non-X11 | 385 passed / 23 deselected，8.64s |
| X11，无 compositor | 21 passed / 1 expected skip / 386 deselected，2.96s |
| X11，有 compositor | 21 passed / 1 expected skip / 386 deselected，2.69s |
| live runtime diagnostic，有 compositor | 12/12 PASS |
| Gemini 335 实机 | 1 passed：100 帧读取与 reopen |
| 实际 Ubuntu 安装检查 | 14/14 PASS |

实际安装检查使用显式、只读命令：

```bash
CONDA_PREFIX=/home/yixiao/miniconda3/envs/neugaze \
/home/yixiao/miniconda3/envs/neugaze/bin/python \
scripts/check_ubuntu_install.py \
--orbbec-sdk-root /home/yixiao/Users/yixiao/Misc/OrbbecSDK_v2 \
--require-overlay --require-test-tools
```

纯 Xvfb 与 `--require-overlay` 的首次组合如预期报告 compositor selection
无 owner；随后按该参数合同在隔离 Xvfb 内显式启动 `xcompmgr`，12 项全部
通过。该失败未被兜底、重试或改写为成功。

## 最终全分支 review 修复波次（第 4 段）

| 提交 | 内容 |
|---|---|
| `1cfc835` | 为 Orbbec read/close native failures 补完整设备与 stage context |

本段针对终审唯一 Important 做窄修：Orbbec `read()` 的 native stages 与
`close()` 的 `pipeline.stop()` 失败现在抛出含完整 device label 和 stage 的
`RuntimeError`，以原 sentinel 为 `__cause__` 并保留 traceback。既有 timeout、
missing frame、metadata、format、dimensions 与 byte-length 显式合同错误不改写。
`stop()` 失败时 `_closed` 保持 false，ownership 可由调用方显式重试；无自动
重试、空帧、缓存或后端回退。

| 证据 | 结果 |
|---|---|
| native-stage 可信 RED | 8 failed / 37 deselected；7 个 read stage 与 stop 均原样冒出 sentinel |
| native-stage GREEN | 8 passed / 37 deselected，0.12s |
| camera focused | 45 passed，0.10s |
| 完整 non-X11 | 392 passed / 23 deselected，8.65s |
| X11，无 compositor | 21 passed / 1 expected skip / 393 deselected，2.91s |
| X11，有 compositor | 21 passed / 1 expected skip / 393 deselected，2.70s |
| live runtime diagnostic，有 compositor | 12/12 PASS |
| Gemini 335 实机 | 1 passed：100 帧读取与 reopen，8.36s |
| 实际 Ubuntu 安装检查 | 14/14 PASS |

实施计划中的 checkbox 是 historical execution template，不机械回填；当前完成度
只以本 progress ledger 的 fresh 命令证据为准。Windows 实机与完整 GUI 人工
验收边界保持不变。

## 校准窗口交接修复（2026-07-27）

- 症状与根因：Gemini 335 在校准启动时，Qt 配置窗口仍占据前台；校准由 Qt 主线程同步执行，同时 HighGUI 在首帧映射前请求全屏，导致窗口交接不可靠。这不是后台 worker、自动重试或后备路径问题。
- RED/GREEN：Task 1 的 Linux 成功顺序断言在基线 RED（仅 `['pipeline']`），异常顺序断言在恢复 Task 1 前基线 RED（`['pipeline', ('error', ...)]`）；恢复实现后三项 handoff 测试 GREEN，相关 GUI 回归 27 passed。Task 2 的调用顺序断言在旧实现 RED（`move` 位于索引 1，缺少 `show`/`wait`）；实现首帧映射后 GREEN，运行时相关回归 103 passed。
- Linux 行为：仅 Linux 在开始校准前 hide Qt 配置窗口并处理事件，且在 `finally` 中 restore 后再进入既有错误呈现；Windows 不改变。OpenCV 先创建普通窗口、`imshow` 首帧、`waitKey(1)`，再移动窗口并请求 fullscreen；不添加 fallback/retry。
- 实测（Gemini 335）：pipeline 构造 0.223s；打开耗时 1.397s；首帧 0.522s，shape `(720, 1280, 3)`。
- 本轮复验：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_config_gui_camera.py tests/test_pipeline_runtime.py -v`：130 passed，9.31s（任务说明中的 126 项为过时计数）；`/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile config_gui_cpu.py my_model_arch/cpu_fast/pipeline.py`：exit 0。
- Gemini 335 真人完整校准仍是用户可见的人工验收项，尚未执行；自动化测试和上述单帧数据不等同于实机完整校准通过。

## README 分节测试契约校正（2026-07-27）

- README 的 3.1/3.2/3.3/3.4 分节及 shell `\\` 续行是既定文档行为；旧测试把跨小标题命令误当作必须连续的单段文本，假设已过时。
- 现行测试先折叠 shell 续行，再以从前一位置继续的 `str.find` 严格检查完整命令及全局顺序；OpenCV 三条修复命令仍须在同一 fenced code block 内连续且内容精确，`pip check` 两行和禁止将其描述为成功的契约未放宽。README 精确检查其四条管理员命令，spec/plan 精确检查完整六条管理员命令。
- 最终验证：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_ubuntu_requirements.py -v` 为 11 passed；同解释器完整 suite 为 483 passed / 1 skipped / 1 deselected（484 selected）。此记录不表示 Gemini 335 真人完整校准通过。


## Linux 独立校准 Worker（2026-07-27）

### 根因与边界

- 生产 stack dump 停在 `my_model_arch/cpu_fast/pipeline.py:1270` 的 `cv2.namedWindow`；当时 Xorg 窗口树中没有 `track`。
- 当前 OpenCV HighGUI GUI backend 是 `QT5 5.15.16`，配置界面父进程是 PySide6 Qt6。同一 Python 进程同时加载两套原生 Qt GUI runtime 时，`cv2.namedWindow` 会阻塞；独立 HighGUI 进程可成功显示窗口，因此根因不是 Xorg、Gemini 335、模型、窗口尺寸或全屏参数。
- Ubuntu 校准不在 Qt6 父进程调用 HighGUI。父进程用 `QProcess` 启动当前解释器的精确 worker 命令：`sys.executable -u -m my_model_arch.cpu_fast.calibration_worker --config <绝对配置路径>`。worker 只加载 pipeline、OpenCV Qt5、X11 desktop backend 与 Gemini 335 RGB `1280x720@30`，不加载 PySide6；父进程隐藏配置窗口、继续 Qt 事件循环，并读取 worker 输出。
- 成功 stdout 必须恰有一行严格 UTF-8 协议：`NEUGAZE_CALIBRATION_RESULT={"calibration_time":"YYYYMMDD_HHMMSS","model_path":"model_weights/YYYYMMDD_HHMMSS/model.pkl"}`。JSON 只能有这两个键；模型路径必须是仓库内与时间戳一致的现存文件。不得从旧模型、缓存或目录时间推断成功；worker 失败、异常退出或协议无效均保留可见原始错误，不重试、不回退。

### 自动化证据与未完成的人工验收

- 隔离回归在 Xvfb 中由 PySide6 `QApplication` 父进程同步等待 `QProcess` 子进程；仅子进程运行 OpenCV Qt5 的 `namedWindow`、`imshow`、`waitKey` 与销毁窗口，并要求正常退出、stdout 精确为 `CALIBRATION_WORKER_WINDOW_OK\n`、stderr 为空。`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_calibration_process_isolation.py -m x11 -v`：1 passed，0.43s，未在 `namedWindow` 挂起。
- worker 协议、Linux GUI `QProcess` 生命周期与隔离回归的本轮组合命令在 Xvfb 下为 73 passed，13.42s：`tests/test_calibration_worker.py`、`tests/test_config_gui_camera.py`、`tests/test_calibration_process_isolation.py`。GUI 测试自身设置的 `QT_QPA_PLATFORM=offscreen` 不传给 OpenCV 子进程；其 Qt5 只有 `xcb` 平台插件，继承该测试变量会原样 abort，不是生产降级路径。
- 以上自动化只证明 worker 协议、父子进程隔离与受控窗口探针，不替代真人 Gemini 335 完整校准。用户仍必须在真实 Ubuntu Xorg 会话中确认可见全屏 `track`、完成校准后的模型与配置更新，以及一次独立 ESC+Q 取消流程；步骤见 `docs/ubuntu-xorg-manual-test.md`。

- 第 1 次独立 fresh full run（先执行）：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -v`：529 passed / 1 skipped / 1 deselected，12.95s。唯一 skip 为需要 `xcompmgr` 的正向 overlay 用例；未传 `--run-orbbec` 的 Gemini 硬件用例保持 deselected。`/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile config_gui_cpu.py my_model_arch/cpu_fast/calibration_worker.py` 与 `git diff --check` 均 exit 0。
- 第 2 次独立 fresh full run（随后执行，并记录于本地 Task 4 report）：同一 pytest 命令为 529 passed / 1 skipped / 1 deselected，19.38s。12.95s 与 19.38s 是按此顺序完成的两次独立运行，不是同一次“最终”运行的两个耗时。

## 真实 Xorg 校准窗口二次修复（2026-07-28）

- 用户在 Gemini 335 实机上启动校准后仍看不到 `track`；worker 已启动，MediaPipe 与 Orbbec 均初始化成功，但没有结果 marker 或 traceback。
- 只读运行证据显示 Gemini 335 RGB `1280x720@30` 正常 streaming，而 output frameset queue 持续满；worker 主线程占用约 100% CPU，Xorg 窗口树没有 `track`，说明主线程没有进入取帧循环。
- 纯 `cv2.namedWindow` 在同一 `DISPLAY=:1` 正常；仅导入 production `pipeline.py` 后再调用 `namedWindow` 则稳定忙循环。进一步二分确认 `torch` 单独正常，`torchvision` import 后 HighGUI 卡死；Orbbec、MediaPipe inference、窗口尺寸和 fullscreen 均不是该二次根因。
- 原 Xvfb 隔离测试只在子进程导入裸 `cv2`，没有导入 production pipeline/torchvision，因此没有覆盖该真实冲突。

### 修复

- `calibration_worker` 不再在模块导入期加载 `RealAction/pipeline/torchvision`。CLI 先创建并销毁专用 HighGUI 预热窗口，再显式延迟导入 production pipeline；正式 `track` 窗口继续由原 pipeline 创建。
- 该顺序不增加重试、fallback、备用 renderer 或旧模型路径；预热失败直接产生原始 traceback 和非零 worker exit。
- 如果事件初始化和预热窗口清理同时失败，保留事件初始化的原始异常与 traceback，并通过异常 note 显式附加清理错误；如果只有清理失败，则直接抛出清理错误。

### 验证

- 正式 Xvfb RED：production-order 子进程因缺少 `initialize_highgui` 退出 1；更早的 pipeline-import 探针在 `namedWindow` 超时，faulthandler 栈停在该调用。
- worker 协议/生命周期、异常保真与 production-order 隔离组合：32 passed，2.73s。
- 真实 Xorg、无相机探针依次输出 `highgui-prewarm-ok`、`production-build-ok`、`namedWindow-ok`、`done`，2.47s 内正常退出；修复前相同 production build 在 20s timeout 内卡死。
- fresh 完整 Xvfb suite：547 passed / 1 skipped / 1 deselected，17.09s；唯一 skip 仍为需要 `xcompmgr` 的正向 overlay 用例。
- `py_compile`（worker 与两项测试）和 `git diff --check` 均 exit 0；现有 `Log/` 保持未跟踪且未修改。
- Gemini 335 真人完整校准仍需用户重新执行并确认可见全屏 `track`、模型/配置更新和 ESC+Q 取消；上述探针不等同于真人校准通过。

## Gemini 335 首次校准帧与 Xorg 全屏修复（2026-07-28）

- 用户实测已进入新校准会话和第 1/9 点，证明独立 worker 与 HighGUI 创建链路已恢复；随后第一帧进入 MediaPipe 时因 `RealAction.milliseconds` 不存在而退出，同时 `track` 仅显示为左上角小窗口。
- 时间戳根因是平台相机重构只保留了 `camera.read()`，删除了旧实现随成功帧更新 MediaPipe timestamp 的逻辑。本轮首版虽然恢复了 `time.monotonic_ns()` 毫秒值，却错误地把两个队列帧落在同一整数毫秒视为异常；该结论已被随后实机校准推翻，并按下节修正。
- 全屏根因由真实 `DISPLAY=:1` 测量确认：Xorg 尚未处理 `moveWindow()` 时，OpenCV Qt5 会静默忽略紧随其后的全屏请求，报告 `fullscreen=0`，图像区约为 `400×210`。现在移动后处理 100 ms 窗口事件，再请求全屏并继续处理 100 ms；随后读取并验证 `WND_PROP_FULLSCREEN`，未进入全屏就明确失败，不继续小窗口校准。
- 该修复没有自动重试、备用窗口实现或 silent fallback。

### 验证

- 新增三项可信 RED：窗口事件顺序不符、忽略全屏请求未报错、首次读帧没有 `milliseconds`；修复后三项均通过。首版“同毫秒必须失败”的测试合同已在下节删除，不再作为正确证据。
- 真实 Xorg 修复后稳定测量：X11 物理画布 `4096×2160`，OpenCV Qt5 HiDPI 逻辑窗口 `fullscreen=1.0`、`rect=(0, 0, 2048, 1080)`。
- Gemini 335 实机 RGB 三帧均为 `1280×720` 并实际进入 `detect_async`；单调时间戳为 `13390960`、`13390988`、`13391021`，原 `AttributeError` 路径未再出现。
- 校准 pipeline、worker 与进程隔离组合：144 passed，7.24s。
- fresh 完整 Xvfb suite：550 passed / 1 skipped / 1 deselected，17.02s；唯一 skip 仍为需要 `xcompmgr` 的正向 overlay 用例。
- 真人 9 点完整数据采集、模型生成和 GUI 回写仍需用户再次执行确认，不能由三帧硬件探针替代。

## Orbbec 队列同毫秒帧修正与加深验证（2026-07-28）

- 用户第二次实测在第 1/9 点得到 `previous=14093958, current=14093958`。这是 Gemini 335 在校准窗口等待 2 秒期间积帧后连续返回队列帧，而不是单调时钟倒退；MediaPipe 只接受严格递增的整数毫秒，首版直接报错策略不正确。
- 当前转换规则是 `max(time.monotonic_ns() // 1_000_000, previous + 1)`。它明确把纳秒单调时钟量化为 MediaPipe 所需的严格递增整数毫秒序列；保留最近 10 个已提交值，不重试相机、不切换后端、不吞掉相机或 MediaPipe 异常。

### 验证

- 同毫秒 RED/GREEN：固定原始时钟为 5 ms，首版在第二帧抛错；修正后三帧得到精确序列 `[5, 6, 7]`。
- Gemini 335 无启动等待的 300 帧全部为 `1280×720` 并进入 `detect_async`，时间戳全部递增。
- Gemini 335 按真实校准时序先等待 2.1 秒再处理 100 帧，前 12 个差值中出现 8 个 `1 ms` 步进，全部 100 帧进入 `detect_async` 并正常清理。
- 生产组合探针实际执行 HighGUI 预热、完整 pipeline、Gemini 335、全屏窗口、2 秒等待和 100 帧 `detect_async`；结果为 `fullscreen=1.0`、`min_delta=1`、`one_ms_steps=8`，正常退出。
- 合成完成链路按当前配置生成 9 点 × 25 样本，执行真实 `MultiTaskLassoCV` 累积训练，并确认 `quality_report.json`、`train_data.jsonl`、`model.pkl` 均生成且模型 fitted。
- 校准 pipeline、worker 与进程隔离组合：145 passed，7.74s。
- fresh 完整 Xvfb suite：551 passed / 1 skipped / 1 deselected，17.68s；唯一 skip 仍为需要 `xcompmgr` 的正向 overlay 用例。
- protobuf `SymbolDatabase.GetPrototype()` 行是依赖库弃用警告，不是 worker 退出原因；本轮不隐藏该警告。
- 真人 9 点的面部采样与 GUI 模型回写仍需用户重试确认；本轮不把硬件探针和合成训练写成真人校准通过。

## README 机器人动作契约修正（2026-07-28）

- 用户指出中英文 README 仍把张嘴、嘟嘴、下颌、微笑和头部动作描述为旧游戏鼠标/键盘操作，与 Ubuntu `robot_terminal` 实现冲突。
- `README-CN.md` 与 `README.md` 现在以 `configs/cpu.yaml` 为事实来源，明确记录四个实际触发：张嘴 `numlock` 打开轮盘、嘟嘴 `left_click` 输出挥手、抬内眉 `num8` 输出舞蹈、仅闭左眼 `extra` 输出停止。内部 ID 不再解释成 Ubuntu 鼠标或键盘事件。
- 四方向注视区域逐项记录为上/下/左/右对应前进一步、后退一步、左转、右转；文档说明保持张嘴选择、闭嘴确认，以及无有效选区时的显式取消协议。
- 两份 README 当时均列出全部七条 `[ROBOT_ACTION]` 输出、取消输出、轮盘半径 400，以及当前只打印词条、尚未启动 GR00T/WBC/SONIC 的边界。旧 `game`、`game_cs`、`game_wz`、`type` 键位表，鼠标点击和 WASD/滚轮映射已从当前控制说明移除。半径 400 的界面已在后续‘透明全屏四分区’阶段被替换。
- 新增参数化文档契约测试，要求两份 README 都包含四个表情条件、四个轮盘方向、七条动作输出和取消输出，并拒绝旧映射文本。
- 文档与安装 focused：30 passed；fresh 完整 Xvfb suite：553 passed / 1 skipped / 1 deselected，17.72s。
- GUI 在本轮期间把 `configs/cpu.yaml` 的 `regression_model_path` 更新为 `model_weights/20260728_162725/model.pkl`；这是用户运行产生的独立配置改动，本轮只读保留，不纳入 README 提交。

## 透明全屏四分区选择层（2026-07-28）

- 用户实测发现张嘴后的旧 Tk 轮盘只占屏幕中心约 `800×800`，白色画布即使设置统一 alpha 仍明显遮挡桌面，红色 Arial 大字也不适合作为机器人动作界面。
- Ubuntu `robot_terminal` 路径不再创建 Tk 圆形轮盘。新 `FullscreenCardinalWheel` 直接使用完整主屏幕坐标；四条‘屏幕角落到中心’的边界形成上、下、左、右四个等面积三角区。命中计算先按屏幕宽高归一化，因此宽屏上四个方向仍保持等面积，屏幕边缘和旧圆外区域均可选择。
- 新 `CardinalOverlay` 在独立 spawn 进程中运行 PySide6 透明全屏窗口。背景不填色，只画低透明分隔线；当前区使用低透明蓝色高亮；中文标签使用系统已安装的 `Noto Sans CJK SC`、深色圆角底板。窗口置顶、点击穿透且不获取焦点。
- 配置事实来源由 `robot_wheel_config.radius: 400` 改为 `robot_wheel_config.layout: fullscreen_cardinal`。旧 `radius`、未知字段、非字符串布局或其他布局均在构造时明确失败，不静默退回圆形轮盘。
- 覆盖层启动要求 X11 compositor。缺少 compositor、主屏幕尺寸与管线不一致、子进程异常、协议消息异常或停止超时都会保留 traceback 并明确失败；不会切回 Tk 或隐藏错误。
- 聚焦回归：`tests/test_cardinal_overlay_x11.py tests/test_pipeline_runtime.py tests/test_robot_actions.py` 为 155 passed / 1 conditional skip；隔离无 compositor Xorg 为 2 passed / 1 positive skip；隔离 `xcompmgr` 联合机器人选择层与凝视层为 4 passed / 2 negative skips；fresh 完整 Xvfb suite 为 565 passed / 2 skipped / 1 deselected，17.83s。
- 真人视觉验收仍未执行。需要在真实 `DISPLAY` 上确认覆盖整个主屏幕、桌面可见、标签大小合适、四个区域高亮正确，并完成每方向至少 5 次闭嘴提交。

## Evaluation 复用标定模型与 HiDPI 覆盖层修复（2026-07-28）

- 已确认不需要每次启动都重新标定。`configs/cpu.yaml` 当前本地 `regression_model_path` 指向 `model_weights/20260728_162725/model.pkl`，文件存在且为 5634 bytes；pipeline 构造时直接 `pickle.load`，不会重新训练。换使用者、移动摄像头或改变屏幕分辨率/缩放/布局时应重新标定。
- 用户直接点击 Evaluation 时失败并非缺少标定，而是覆盖层尺寸校验混用了 X11 物理像素和 Qt HiDPI 逻辑像素。真实 `DISPLAY=:1` 证据为：Qt logical `(2048, 1080)`、`devicePixelRatio=2.0`、Qt physical `(4096, 2160)`，X11 pipeline `(4096, 2160)`。
- 新校验显式计算 `round(Qt logical × devicePixelRatio)` 后再与 pipeline 物理尺寸比较；100%、125%、200% 缩放均有单元测试。比例为 0、负数或 NaN 仍明确失败；真正的物理尺寸不一致也保留 logical、DPR、physical 和 pipeline 四组诊断值，不关闭错误。
- 当前真实 `DISPLAY=:1` 已实际完成 `CardinalOverlay((4096, 2160)).start()`、监督检查和同步 `stop()`，输出 `REAL_DISPLAY_OVERLAY_START_STOP_OK`，此前的 screen mismatch 不再出现。
- focused：HiDPI 覆盖层、Evaluation pipeline、动作合同和 GUI 配置 203 passed / 1 conditional skip；隔离 `xcompmgr` 的机器人选择层与凝视层联合测试 4 passed / 2 negative skips。fresh 完整 Xvfb suite 为 571 passed / 2 skipped / 1 deselected，17.97s。

## 头姿四方向选择与非阻塞 Evaluation（2026-07-28）

- 用户实测认为凝视选择误差过大。Ubuntu `robot_terminal` 路径现已停止使用凝视坐标选轮盘：张嘴仍负责打开透明全屏四分区，MediaPipe 头姿俯仰/偏航负责选择，闭嘴负责提交。Windows 桌面/游戏路径未改。
- 固定映射为：抬头 → `move_forward_step` / 前进一步，低头 → `move_backward_step` / 后退一步，向左转头 → `turn_left` / 左转，向右转头 → `turn_right` / 右转。默认俯仰阈值 `10°`、偏航阈值 `12°`；阈值内为中立死区并清除选区。双轴同时越界时，采用相对各自阈值偏移更大的方向。
- `robot_wheel_config` 的事实来源现在精确要求 `layout: fullscreen_cardinal`、`selection: head_pose`、`yaw_threshold_degrees` 和 `pitch_threshold_degrees`。缺字段、未知字段、非数值、布尔值、非有限值或 `(0, 45]` 之外的阈值均直接失败；不回退到凝视或旧圆形轮盘。
- Ubuntu 机器人路径不再启动 gaze mouse controller，也丢弃 `predicted_position` 的鼠标输出；透明全屏区域仅作为头部方向反馈，不发送系统键鼠事件。
- GUI 的 Evaluation 已从 Qt 主线程移到受监督的 `QThread`。运行时配置标签页仍可切换查看；相机确认/切换和重新标定按钮因资源冲突明确禁用，Evaluation 按钮变为 `Stop Evaluation`。停止、ESC+Q 和关窗均保留线程/流水线所有权，直到 worker 完成；worker 原始异常和 traceback 会显示，线程启动失败会清理流水线并保留主错误。
- README 中英文版和 `docs/ubuntu-robot-terminal-acceptance.md` 已同步为头姿选择、阈值、中立取消、后台 Evaluation 和按钮状态；旧“保持张嘴并用注视选择”由文档契约测试拒绝。

验证记录：

| 验证 | 结果 |
|---|---|
| 头姿选区、pipeline、动作契约、GUI focused | `211 passed / 1 skipped`，15.62s；skip 为需要无 compositor 隔离显示的条件测试 |
| Xvfb + `xcompmgr` 透明层 | `4 passed / 2 skipped / 17 deselected`，2.74s；两个 skip 为无 compositor negative 用例 |
| Xvfb 无 compositor fail-fast | `4 passed / 2 skipped / 17 deselected`，2.49s；两个 skip 为需要 `xcompmgr` 的 positive 用例 |
| fresh 完整 Xvfb suite | `579 passed / 2 skipped / 1 deselected`，18.78s；两个 skip 均为 compositor 条件分支，Gemini 硬件测试未带开关因此 deselected |
| Gemini 335 RGB 硬件 | `tests/test_orbbec_hardware.py --run-orbbec`：`1 passed`，8.35s；读取 100 帧、关闭、重开并再读 1 帧 |
| 真人头姿与 GUI 视觉验收 | 未执行；抬头/低头/左右转头方向、10°/12° 舒适度、闭嘴提交和中立取消仍需用户面对 Gemini 335 验证 |

## Evaluation 独立进程与 GUI 可交互修复（2026-07-28）

- 用户真实运行确认上一阶段的 `QThread` 方案仍无法点击 GUI。该结果推翻了“线程 API 已返回即可证明 Qt 可响应”的假设：MediaPipe/OpenCV/Python 推理循环仍与 Qt 主进程共享解释器和运行库。上一节的 QThread 实现现已被本节完整替代，不再作为当前实现。
- Ubuntu Evaluation 现由 `QProcess` 启动 `my_model_arch.cpu_fast.evaluation_worker`。GUI 主进程只负责标签页、配置控件、按钮状态及 stdout/stderr 转发；相机、MediaPipe、头姿选择层和动作输出全部由子进程拥有。Windows 仍走原同步 pipeline 路径。
- Worker 内部采用监督主线程与 `neugaze-evaluation` 线程：Evaluation 线程执行可能阻塞的 Orbbec `wait_for_frames()`；监督主线程接收 `SIGINT`/`SIGTERM`。真实线程栈证明单纯在主线程设置 Python 标志无法中断 Orbbec C 调用，因此新增 `request_evaluation_stop()`，由监督线程关闭相机以解除阻塞，随后 Evaluation 原路径完成 wheel、overlay、camera 和 desktop 清理。
- `Stop Evaluation` 与 ESC+Q 只发送异步停止，不在 GUI 线程等待。5 秒后 worker 仍存活时会在 Terminal 明确打印超时并发送 `kill`；随后非零退出仍显示完整错误，不伪装成成功。
- Evaluation 运行期间可切换和操作其他配置标签页。相机确认、切换和重新标定继续禁用，因为它们会争用子进程持有的 Gemini 335；普通配置控件不再错误访问 `None` pipeline。关窗在 worker 完成前仍明确拒绝。

验证记录：

| 验证 | 结果 |
|---|---|
| worker、GUI、pipeline focused | `180 passed`，16.44s；覆盖独立 QProcess、专用 Evaluation 线程、SIGTERM 相机中断、异步停止、5 秒超时 kill、原始异常、热键和关窗 |
| 头姿选择与 GUI 联合回归 | `215 passed / 1 skipped`，16.21s；skip 为需要无 compositor 的条件用例 |
| fresh 完整 Xvfb suite | `586 passed / 2 skipped / 1 deselected`，19.87s；两个 skip 为 compositor 条件分支，Gemini 硬件用例未带开关因此 deselected |
| Xvfb + `xcompmgr` 透明层 | `4 passed / 2 skipped / 17 deselected`，2.67s；两个 skip 为无 compositor negative 用例 |
| 真实 worker + Gemini 335 | Evaluation 正常启动；向精确父 PID 发送与 `QProcess.terminate()` 相同的 SIGTERM 后 exit 0，无 traceback |
| 真实 ConfigWindow + QProcess + Gemini 335 | Evaluation 连续运行 5 秒时成功切换标签页并调用三个配置控件，输出 `NEUGAZE_GUI_RESPONSIVE`；Stop 后 10 秒门限内正常清理，输出 `NEUGAZE_GUI_EVALUATION_STOPPED`，无错误对话框 |
| 停止后的相机释放 | `tests/test_orbbec_hardware.py --run-orbbec`：`1 passed`，8.34s；再次读取 100 帧、关闭、重开并读取 1 帧 |

## MediaPipe protobuf 弃用警告收窄（2026-07-28）

- 终端中的 `SymbolDatabase.GetPrototype()` 来自 MediaPipe 0.10.14 的
  `packet_getter.py` 调用 protobuf 4.25 兼容接口，不代表标定、Evaluation
  或 Gemini 335 读取失败。
- 校准 worker、Evaluation worker 和配置 GUI 入口现在只过滤
  `google.protobuf.symbol_database` 发出的这一条完整弃用文本。GUI 原先的
  `warnings.filterwarnings("ignore")` 全局忽略已删除；其他 warning、相机错误
  和 traceback 继续原样显示。
- 无摄像头真实 MediaPipe protobuf roundtrip 成功，`score=0.75`；目标警告
  未出现，同时故意发出的无关 `UserWarning` 仍出现在 stderr。
- worker focused：`36 passed`。首次 pytest 调用被系统 ROS 的 Python 3.12
  插件自动发现及其缺失 `lark` 阻断，使用项目隔离设置
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` 后测试正常通过；该环境问题与代码修改
  无关。
- fresh 完整 Xvfb suite：`587 passed / 2 skipped / 1 deselected`，19.44s；
  两个 skip 为需要 `xcompmgr` 的正向覆盖层用例，Gemini 335 硬件用例因未传
  `--run-orbbec` 保持 deselected。

## 头姿选择防误提交状态机（2026-07-28）

- 用户实测指出左右转头会让 `jawOpen` 短暂跌破阈值；旧轮盘把这一帧
  `numlock=True→False` 直接解释为闭嘴确认，可能在方向尚未稳定时提交。
- Ubuntu 机器人轮盘不再依据瞬时表达式下降关闭。方向需连续稳定 5 个新鲜
  MediaPipe 处理帧才锁定；轮盘线程以 observation generation 去重，不能把同一
  摄像头帧的多次轮询累计为稳定帧。
- 锁定后必须回到俯仰/偏航中立死区，并连续 3 个有效帧重新识别到张嘴，随后
  连续 5 个有效闭嘴帧才提交。转头期间的口型下降不会提交；回正不会清除已锁定
  高亮。
- 人脸或 blendshape 丢失会显式发布无效观测、清空临时候选并解除闭嘴确认资格，
  不会伪造成闭嘴；恢复后必须重新完成“中立位置张嘴”步骤。未锁定方向时，中立
  闭嘴 30 个有效帧只输出显式取消行。
- Windows 桌面轮盘路径未改。README 中英文版和中文真人验收文档已同步为
  “张嘴打开 → 稳定选向 → 回正并继续张嘴 → 闭嘴提交”。
- focused 状态机、pipeline、动作和文档：`159 passed / 3 deselected`，5.37s。
  fresh 完整 Xvfb suite：`594 passed / 2 skipped / 1 deselected`，19.37s；
  带 `xcompmgr` 的覆盖层正向集成：`4 passed / 2 conditional skips / 19 deselected`，
  2.62s。
- 真实 `DISPLAY=:1` + Gemini 335 Evaluation 中立运行 5 秒，无任何
  `[ROBOT_ACTION]` 或取消输出，SIGTERM exit 0；随后硬件测试再次读取 100 帧、
  关闭、重开并读取 1 帧，`1 passed`，8.40s。真人转头/回正/闭嘴序列仍需用户
  按中文验收文档执行，不能由中立硬件探针代替。
