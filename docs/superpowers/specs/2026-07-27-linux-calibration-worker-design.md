# Linux 独立校准 Worker 设计

## 问题与证据

Ubuntu 24.04 Xorg 下，配置界面由 PySide6/Qt6 创建，当前
`opencv-contrib-python==4.11.0.86` 的 HighGUI 则由 Qt 5.15 构建。生产路径
同时加载两套 Qt runtime 后，点击 `Start Calibration` 会稳定阻塞在
`cv2.namedWindow()`；此时 Xorg 窗口树中不存在 `track` 窗口。

独立 OpenCV 进程可以创建并显示同一个 HighGUI 窗口，因此根因不是 Xorg、
Gemini 335、模型初始化、窗口尺寸或全屏参数，而是 Qt5 HighGUI 与
PySide6/Qt6 在同一进程中的原生 GUI runtime 冲突。

## 目标与范围

- Ubuntu 点击校准后必须启动可见的 OpenCV 全屏校准界面。
- Gemini 335 继续只读取 RGB 1280×720@30 FPS。
- 复用现有校准点、采样、训练、成功/失败画面和 ESC+Q 退出逻辑。
- Qt 主界面在校准期间保持事件循环，不再调用同进程 HighGUI。
- Windows 继续使用现有同进程校准路径。
- 不修改 evaluation、表情识别、机器人词条、轮盘和 SONIC 规划。
- 不增加相机后端回退、自动重试或伪成功结果。

## 架构

Linux 校准通过一个专用 Python 子进程执行：

1. Qt 主界面关闭自己的摄像头预览。
2. 主界面使用 `QProcess` 启动当前解释器：
   `python -u -m my_model_arch.cpu_fast.calibration_worker --config <配置路径>`。
3. 子进程只加载 pipeline、OpenCV Qt5、X11 desktop backend 和 Gemini 335，
   不加载 PySide6。
4. 子进程执行现有 `RealAction.start_calibration()`；所有 HighGUI 调用保持在
   子进程内。
5. 主进程隐藏配置窗口，但 Qt6 事件循环继续运行并读取子进程输出。
6. 子进程完成资源清理后输出唯一的一行成功结果。
7. 主进程严格校验结果，恢复配置窗口并更新回归模型路径。

只新增一个职责明确的 worker 模块和一组直接的 `ConfigWindow` 生命周期方法，
不新增 manager、factory、统一任务框架或备用校准实现。

## Worker 输入与结果协议

Worker 只接收一个必需参数 `--config`。配置路径必须存在并由 YAML 解析为现有
CPU 配置结构；模型和相对输出路径仍以仓库根目录为工作目录。

成功协议为一行 UTF-8：

```text
NEUGAZE_CALIBRATION_RESULT={"calibration_time":"YYYYMMDD_HHMMSS","model_path":"model_weights/YYYYMMDD_HHMMSS/model.pkl"}
```

约束：

- stdout 中必须恰好存在一个结果行；
- JSON 必须恰好包含 `calibration_time` 和 `model_path`；
- `calibration_time` 必须与 `model_path` 的目录一致；
- `model_path` 必须是仓库内的相对路径，且文件真实存在；
- 只有 pipeline 正常完成并清理资源后才允许输出结果行。

MediaPipe、训练进度和既有日志可以继续输出；结果行通过固定字节前缀识别，不能
通过“最新模型目录”或旧缓存推断成功。

## 主进程生命周期

Linux `ConfigWindow.start_calibration()` 不再初始化或调用本地 pipeline：

- 拒绝在已有校准进程运行时再次启动；
- 先关闭 preview，随后创建并连接一个 `QProcess`；
- 使用 `sys.executable`、模块入口和 `current_config_path`；
- `waitForStarted` 失败时保留 `QProcess.errorString()` 并显示 traceback；
- 进程启动成功后禁用摄像头相关按钮、隐藏配置窗口；
- stdout/stderr 原始字节实时转发到父终端并分别累计；
- `finished` 后先恢复配置窗口，再判断退出状态和解析结果；
- 正常结果沿用现有模型路径更新、保存配置及是否重启 preview 的询问。

若 GUI 收到关闭事件时校准仍在运行，关闭请求被明确拒绝，配置窗口恢复并提示
用户先在校准界面使用 ESC+Q 结束。主进程不会无提示地遗留、终止或替换 worker。

Windows `start_calibration()` 保持现有同步调用和异常 identity 行为。

## 错误处理

- Worker 未启动、异常退出、非零退出、重复/缺失/无效结果、越界模型路径或模型
  文件缺失均为可见失败。
- 子进程 Python traceback 完整保留在 stderr，并包含在父进程错误信息中。
- 父进程恢复窗口后才显示错误对话框。
- Worker 内 pipeline/desktop 清理失败附加到原始异常，不覆盖根因。
- 失败后禁用当前 camera actions；不自动重启、不切换 V4L2、不选择旧模型。
- 协议解析不返回空值、默认路径或最近一次成功结果。

## 测试与验收

自动化测试：

- Worker 使用当前配置构造 pipeline，并在成功清理后输出唯一严格结果；
- pipeline、desktop 或清理错误保持 traceback 和非零退出；
- Linux GUI 使用 `QProcess`，不调用本地 `initialize_pipeline()` 或
  `pipeline.start_calibration()`；
- stdout/stderr 实时转发并累计；
- 正常、异常、崩溃、重复结果、无效 JSON、路径越界和模型缺失均覆盖；
- 运行中重复点击与 GUI 关闭请求明确失败；
- Windows 同步校准测试保持通过；
- 完整 pytest、`py_compile` 和隔离 X11 集成保持通过。

人工验收：

1. Gemini 335 插入，启动 `python config_gui_cpu.py`。
2. 点击 `Start Calibration`，确认 Qt 配置窗口隐藏且 `track` 前台全屏出现。
3. 完成一次真实校准，确认模型生成、配置更新和 preview 重启询问。
4. 再次校准并用 ESC+Q 中断，确认子进程退出、主窗口恢复且没有伪成功模型。
5. 人工验收完成前，文档不得把自动化测试描述为 Gemini 335 完整校准通过。
