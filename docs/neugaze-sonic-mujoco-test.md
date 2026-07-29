# NeuGaze × SONIC MuJoCo 联调

本文只覆盖 Ubuntu 24.04 上的 MuJoCo 联调，不包含 Windows，也不把面部动作当作实体机器人的物理急停。

## 1. 启动 MuJoCo

终端 A：

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl
python gear_sonic/scripts/run_sim_loop.py
```

## 2. 启动带 NeuGaze 端点的 SONIC

终端 B：

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl/gear_sonic_deploy
./deploy.sh \
  --motion-data reference/neugaze_robot_action \
  --neugaze-endpoint ipc:///tmp/neugaze-sonic.sock \
  sim
```

启动日志必须出现：

```text
[NeuGaze] action server listening at ipc:///tmp/neugaze-sonic.sock
```

随后在终端 B 按 `]` 启动控制。保持默认 reference-motion 模式，不要按 Enter 进入 planner。

## 3. 不使用摄像头先验证 IPC

终端 C：

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze/.worktrees/ubuntu-xorg-port
conda activate neugaze
python scripts/send_sonic_action.py turn_left
python scripts/send_sonic_action.py wave
python scripts/send_sonic_action.py stop
```

每条成功命令应打印 `[SONIC_ACTION_ACCEPTED]`。SONIC 端应分别打印动作目录名；`stop` 应打印：

```text
[NeuGaze] reset reference motion
```

`stop` 与 reference-motion 模式的 `R` 完全一致：暂停当前动作、回到第 0 帧并重新初始化朝向。它不是 planner momentum reset，也不是设置 `operator_state.stop=true` 的全局急停。

若 SONIC 未启动、endpoint 不一致或请求被拒绝，发送脚本必须非零退出并显示原始错误；不要把失败结果记为动作成功。

## 4. 切换 NeuGaze 为 SONIC 输出

把 `configs/cpu.yaml` 改为：

```yaml
robot_action_output_config:
  type: sonic_ipc
  endpoint: ipc:///tmp/neugaze-sonic.sock
  timeout_ms: 1000
```

然后启动：

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze/.worktrees/ubuntu-xorg-port
conda activate neugaze
python config_gui_cpu.py
```

完成相机确认、校准并开始 evaluation。两个轮盘的 8 个动作应驱动对应 reference motion；仅闭左眼触发 `stop` 时应执行上述 reference `R` 行为。NeuGaze 只有收到 SONIC 的 `accepted` 回复后才打印 `[ROBOT_ACTION]`。

## 5. 建议实测顺序

1. 用 `send_sonic_action.py` 依次验证 8 个动作各 1 次。
2. 播放前进、后退、舞蹈各 1 次，在动作中途发送 `stop`，对比键盘 `R`。
3. 再接入 NeuGaze，两个轮盘的 8 个动作各验证 3 次。
4. 每个动作播放中途各闭左眼 1 次，确认动作立即停止并回到第 0 帧。
5. 停止 SONIC 后触发一次 NeuGaze 动作，确认 evaluation 显式报通信超时，不继续伪装成功。

## 6. 恢复 Terminal 验证模式

不连接 SONIC 时使用：

```yaml
robot_action_output_config:
  type: terminal
```

两种模式是显式互斥的；`sonic_ipc` 失败不会自动回退到 `terminal`。
