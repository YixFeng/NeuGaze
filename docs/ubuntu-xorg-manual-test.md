# Ubuntu Gemini 335 独立校准手工验收

最后更新：2026-07-27

## 验收边界

本文件只覆盖 Ubuntu Xorg 上的 Gemini 335 真人校准。自动化 worker、GUI、Xvfb
和 100 帧硬件 smoke 都不能替代本验收：它们不证明真人可见的校准 UI、九点采样、
模型训练、配置更新或用户接受。

## 启动

在已连接 Gemini 335、已登录 Xorg 的普通用户会话中执行：

```bash
conda activate neugaze
cd /home/yixiao/Users/yixiao/Misc/NeuGaze/.worktrees/ubuntu-xorg-port
python config_gui_cpu.py
```

不要使用 root，也不要设置 `QT_QPA_PLATFORM=offscreen`。若启动、摄像头或 worker
失败，应保留并报告原始错误；不要重试、切换后端或使用旧模型伪造成功。

## 完整校准通过条件

1. 确认 GUI 选择 Gemini 335 的 RGB `1280x720@30`，然后点击 `Start Calibration`。
2. 确认 Qt 配置窗口隐藏，前台可见全屏 OpenCV `track` 窗口；它不得卡在创建窗口阶段。
3. 按既有流程完成整次真人校准。结束后确认 worker 正常退出、主配置窗口恢复，且新模型已生成并写入配置。
4. 另行启动第二次校准，使用 ESC+Q 取消。确认 worker 退出、主窗口恢复，且取消不会伪造成功结果、更新为不存在的模型或悄悄回退到旧模型。

只有四项均由真人观察并记录后，才能把 Gemini 335 完整校准标记为通过。

## 自动化与硬件 smoke 的范围

Xvfb 隔离回归只证明 PySide6 Qt6 父进程可以等待 OpenCV Qt5 子进程完成一个小窗口探针。显式 `--run-orbbec` 的 100 帧测试只证明当前 Gemini 335 的 camera ownership、RGB 读取、关闭与重开；即使通过，也不证明 `track` 可见、真人校准完成、模型训练成功或本手工验收通过。
