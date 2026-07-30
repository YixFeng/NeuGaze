# NeuGaze 控制 SONIC

本文简要说明如何用 NeuGaze 控制 SONIC 的 MuJoCo 仿真和 G1 实机。

以下示例默认：

- NeuGaze：`/home/yixiao/Users/yixiao/Misc/NeuGaze`
- WBC：`/home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl`
- NeuGaze 与 SONIC 部署进程运行在同一台电脑上

如果仓库位于其他位置，请替换命令中的绝对路径。

## 1. NeuGaze 配置

仿真和实机使用相同配置。确认 `configs/cpu.yaml` 包含：

```yaml
robot_action_output_config:
  type: sonic_ipc
  endpoint: ipc:///tmp/neugaze-sonic.sock
  timeout_ms: 1000
```

`sonic_ipc` 必须且只能包含上述三个字段。`ipc://` 是本机通信，不能连接另一台物理电脑。

## 2. MuJoCo sim2sim

### 终端 1：启动 MuJoCo

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl
source .venv_sim/bin/activate
python gear_sonic/scripts/run_sim_loop.py
```

如果尚未创建 `.venv_sim`，先运行一次：

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl
bash install_scripts/install_mujoco_sim.sh
```

### 终端 2：启动 SONIC

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl/gear_sonic_deploy
./deploy.sh \
  --motion-data reference/neugaze_robot_action \
  --input-type manager \
  --neugaze-endpoint ipc:///tmp/neugaze-sonic.sock \
  sim
```

看到以下日志后，说明 NeuGaze 动作服务已经启动：

```text
[NeuGaze] action server listening at ipc:///tmp/neugaze-sonic.sock
```

然后：

1. 在 SONIC 终端按 `]` 启动控制。
2. 在 MuJoCo 窗口按 `9` 释放机器人。
3. 等机器人站稳后再启动 NeuGaze。

### 终端 3：启动 NeuGaze

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze
conda activate neugaze
python config_gui_cpu.py
```

## 3. G1 实机

部署前必须先完成 SONIC 官方实机环境安装，并确认电脑通过机器人网口接入 `192.168.123.*` 网络。建议先在 MuJoCo 中完整验证八个动作和停止动作。

### 终端 1：启动实机 SONIC

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl/gear_sonic_deploy
./deploy.sh \
  --motion-data reference/neugaze_robot_action \
  --input-type manager \
  --neugaze-endpoint ipc:///tmp/neugaze-sonic.sock \
  real
```

`real` 会自动查找连接机器人 `192.168.123.*` 网络的本机网卡。确认模型、网卡和机器人状态无误后，在 SONIC 终端按 `]` 启动控制。

### 终端 2：启动 NeuGaze

NeuGaze 必须与上述 SONIC 部署进程运行在同一台电脑：

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze
conda activate neugaze
python config_gui_cpu.py
```

实机运行时应始终有人准备使用物理急停，并在 SONIC 终端保留键盘：

- `O`：立即停止控制并退出 SONIC。
- 遥控器 `Select`：使用 gamepad 接口时立即停止控制并退出。
- NeuGaze 的闭左眼“停止”：停止当前参考动作并回到第 0 帧，等价于 reference-motion 模式的 `R`，不是物理急停，也不会退出 SONIC。

## 4. 不使用摄像头测试通信

先启动 SONIC，再在 NeuGaze 仓库运行：

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze
conda activate neugaze

python scripts/send_sonic_action.py turn_left
python scripts/send_sonic_action.py wave
python scripts/send_sonic_action.py stop
```

成功时 NeuGaze 端会打印：

```text
[SONIC_ACTION_ACCEPTED]
```

如果 SONIC 未启动、端点不一致或动作被拒绝，命令会直接报错，不会自动回退为 Terminal 输出。

## 5. 只测试识别，不控制 SONIC

将 `configs/cpu.yaml` 改为：

```yaml
robot_action_output_config:
  type: terminal
```

此模式只在启动 NeuGaze 的终端打印动作词条，不发送机器人控制命令。
