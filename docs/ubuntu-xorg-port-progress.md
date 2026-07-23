# Ubuntu 24.04 Xorg 移植进度

最后更新：2026-07-23

## 协作规则

- 本文件是 Ubuntu 移植的共享进度入口。
- agent 开始工作前先阅读设计、实施计划和本文件。
- 每次任务状态、验证证据、阻塞项或接口约定变化后更新本文件。
- 不把“代码已写”视为完成；只有对应验证通过后才能标记完成。
- 不隐藏错误，不记录未经命令输出支持的“已通过”状态。

## 文档入口

- 设计：`docs/superpowers/specs/2026-07-23-ubuntu-xorg-port-design.md`
- 实施计划：设计文档经用户书面确认后创建
- 本进度：`docs/ubuntu-xorg-port-progress.md`

## 已确认决策

- 目标系统：Ubuntu 24.04 x86-64
- 桌面会话：Xorg
- Windows：保留现有支持
- 功能范围：GUI、预览、校准、评估、凝视鼠标、完整键鼠映射、轮盘、透明凝视层
- Ubuntu 摄像头：Orbbec Gemini 335
- 摄像头数据：仅 RGB，`1280x720 @ 30 FPS`
- Ubuntu 摄像头 API：Orbbec SDK v2 + `pyorbbecsdk2`
- Windows 摄像头：本次不改
- 权限：安装阶段需要 `sudo` 时先请求用户；运行阶段不使用 root
- 失败策略：fail fast，无 V4L2、OpenCV、Wayland、主线程或旧缓存回退
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
- Python Orbbec 绑定：尚未安装
- 仓库初始状态：`main` 与 `origin/main` 同步，开始设计时无本地改动

## 阶段状态

| 阶段 | 状态 | 验证 |
|---|---|---|
| 仓库与平台依赖摸底 | 完成 | 已记录 Win32、DirectShow、pywin32、keyboard、透明层和屏幕 API 调用 |
| 需求确认 | 完成 | 用户批准 Xorg、双平台、完整功能、非 root 运行和 Gemini 335 RGB |
| 设计评审 | 完成 | 用户分三部分批准设计 |
| 设计文档 | 完成 | 提交 `eec9d8f`，等待用户书面复核 |
| 实施计划 | 未开始 | 设计文档复核后创建 |
| 实现 | 未开始 | 依实施计划执行 |
| 自动化验证 | 未开始 | 依设计中的测试矩阵执行 |
| Gemini 335 实机验收 | 未开始 | 需要连接设备和 Xorg 会话 |

## 当前工作

设计文档已完成自检并提交。下一步是请用户复核书面设计，然后创建逐任务实施计划。

## 验证日志

| 日期 | 命令或检查 | 结果 |
|---|---|---|
| 2026-07-23 | `uname -a` | Ubuntu 24.04 系列内核，x86-64 |
| 2026-07-23 | 仓库 Windows 依赖扫描 | 主路径包含 pywin32、WinDLL、DirectShow、Win32 overlay 与输入调用 |
| 2026-07-23 | Orbbec 目录与系统库扫描 | 找到源码、v2.9.3 系统安装和 udev 规则 |
| 2026-07-23 | 所有 Conda 环境检查 `pyorbbecsdk` | 均未安装 |
| 2026-07-23 | 设计文档占位符、一致性、范围和歧义自检 | 通过，提交 `eec9d8f` |

## 阻塞项

当前无实施阻塞。开始实现前仍需用户复核已写入的设计文档。
