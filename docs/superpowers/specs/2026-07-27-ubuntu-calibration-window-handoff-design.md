# Ubuntu 校准窗口交接修复设计

## 背景与根因

Ubuntu 24.04 Xorg 下，`Start Calibration` 按钮的 Qt 槽函数同步执行完整校准流程。校准期间 Qt 事件循环无法继续处理配置窗口事件，因此配置窗口会显示为无响应。

校准画面由 OpenCV HighGUI 创建。当前代码在显示第一帧之前请求全屏；在 GNOME/Xorg 实测中，该请求没有得到预期的全屏窗口，校准窗口可能以普通窗口出现并被配置窗口遮挡。

分段实机检查已经排除模型和 Gemini 335：

- pipeline 构造约 0.22 秒；
- Gemini 335 RGB 1280×720@30 FPS 打开约 1.40 秒；
- 首帧读取约 0.52 秒，形状为 `(720, 1280, 3)`。

MediaPipe 的 EGL、XNNPACK 和 feedback tensor 输出均为初始化信息，不是异常。

## 范围

本修复只改变 Linux/Ubuntu 的校准窗口交接：

1. 校准开始前隐藏配置窗口，并立即处理已经排队的 Qt 显示事件。
2. OpenCV 校准窗口先显示一帧并处理窗口事件，再请求全屏。
3. 校准正常结束后恢复配置窗口。
4. 校准抛出异常时先恢复配置窗口，再显示包含原始 traceback 的错误对话框，并重新抛出同一异常。

Windows 行为保持不变。摄像头后端、识别算法、校准采样、模型训练和机器人动作输出均不在本次范围内。

## 设计

`ConfigWindow.start_calibration()` 在 Linux 路径中负责 Qt 配置窗口与 OpenCV 校准窗口之间的可见性交接。它不创建工作线程或备用路径，完整校准仍在主线程执行，避免把 OpenCV HighGUI 移到非主线程。

`IntegratedRegressionMediaPipeline.setup_window()` 负责 OpenCV 窗口创建顺序：

1. 创建可调整大小的窗口；
2. 显示一张与屏幕尺寸一致的空白首帧；
3. 调用一次短时 `waitKey`，使 Xorg/窗口管理器完成窗口映射；
4. 移动到屏幕原点并请求全屏。

没有全屏失败后的静默降级。如果 OpenCV 调用抛出异常，异常沿现有调用链直接传播。

## 错误处理

- 使用 `finally` 保证 Linux 配置窗口在校准返回或抛错后恢复。
- 现有 `QMessageBox.critical` 继续显示完整 `traceback.format_exc()`。
- 不捕获后返回默认成功值，不重试，不切换相机后端。
- Windows 不执行隐藏/恢复逻辑。

## 测试

自动化回归测试覆盖：

1. Linux 校准调用前隐藏配置窗口并刷新 Qt 事件；
2. Linux 校准成功后恢复配置窗口；
3. Linux 校准异常后仍恢复配置窗口，原异常身份保持不变；
4. Windows 校准不隐藏配置窗口；
5. OpenCV 窗口在请求全屏前已经显示首帧并处理一次事件；
6. 既有 GUI camera 和 pipeline runtime 测试继续通过。

人工验收使用 Gemini 335：

1. 启动 `python config_gui_cpu.py`；
2. 点击 `Start Calibration`；
3. 配置窗口消失，校准画面出现在前台并全屏；
4. 完成或退出校准后配置窗口恢复；
5. 终端持续保留真实异常和校准进度输出。
