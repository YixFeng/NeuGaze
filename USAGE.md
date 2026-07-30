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

### 为什么推荐 manager

实机联调推荐使用 `--input-type manager`，而不是把输入固定为 `gamepad`。manager 会同时创建 Keyboard、Gamepad 和 ZMQ 等输入接口，但任何时刻只有当前选中的接口负责常规控制：

- 默认使用 Keyboard。
- 按 `Shift+2`（输入字符 `@`）切换到 Gamepad 后，遥控器的按钮和摇杆功能完整可用。
- 按 `Shift+1`（输入字符 `!`）可以切回 Keyboard。
- 键盘 `O` 始终由 manager 全局接收，即使当前使用 Gamepad，也能立即停止控制并退出。
- NeuGaze IPC 动作服务独立于 manager 的输入选择，Keyboard 或 Gamepad 被选中时都能接收 NeuGaze 动作。

每次切换输入接口都会触发安全复位：关闭 Planner、返回参考动作第 0 帧、复位朝向和移动状态，并清除上一接口留下的控制输入。

### 终端 1：启动实机 SONIC

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl/gear_sonic_deploy
./deploy.sh \
  --motion-data reference/neugaze_robot_action \
  --input-type manager \
  --neugaze-endpoint ipc:///tmp/neugaze-sonic.sock \
  real
```

`real` 会自动查找连接机器人 `192.168.123.*` 网络的本机网卡。

推荐启动顺序：

1. 确认机器人周围无人、物理急停可用，操作员保持在安全位置。
2. 确认模型、网卡和机器人状态无误。
3. 在 SONIC 终端按 `]`，从默认 Keyboard 接口启动控制。
4. 按 `Shift+2`（`@`）切换到 Gamepad。终端应打印 `Switched to: GAMEPAD (safety reset triggered)`。
5. 保持普通参考动作模式，不要按 `F1` 进入 Planner。
6. 先用遥控器验证站立、动作播放、动作复位和退出，再启动 NeuGaze。

如果明确不需要键盘切换和全局 `O`，也可以使用仅 Gamepad 模式：

```bash
cd /home/yixiao/Users/yixiao/WBC/GR00T-WholeBodyControl/gear_sonic_deploy
./deploy.sh \
  --motion-data reference/neugaze_robot_action \
  --input-type gamepad \
  --neugaze-endpoint ipc:///tmp/neugaze-sonic.sock \
  real
```

仅 Gamepad 模式下，需要按遥控器 `Start` 启动控制，并使用 `Select` 停止控制和退出。NeuGaze 实机联调仍推荐 manager。

### 终端 2：启动 NeuGaze

NeuGaze 必须与上述 SONIC 部署进程运行在同一台电脑：

```bash
cd /home/yixiao/Users/yixiao/Misc/NeuGaze
conda activate neugaze
python config_gui_cpu.py
```

### manager 全局按键

| 键盘按键 | 功能 |
| --- | --- |
| `Shift+1`（`!`） | 切换到 Keyboard |
| `Shift+2`（`@`） | 切换到 Unitree Gamepad |
| `Shift+3`（`#`） | 切换到 ZMQ streaming |
| `O` | 无论当前接口是什么，立即停止控制并退出 |
| `F` | 报告电机温度 |

### 遥控器：普通参考动作模式

NeuGaze 的八个动作属于 reference motion，因此实机验证和 NeuGaze 联调应保持在此模式。

| 遥控器输入 | 功能 |
| --- | --- |
| `Start` | 在仅 Gamepad 模式下启动控制；manager 已用 `]` 启动时不需要重复操作 |
| `A` | 播放或重新播放当前参考动作 |
| `B` | 中止当前参考动作，返回第 0 帧并暂停 |
| `L1` / `R1` | 上一个 / 下一个参考动作 |
| 十字键左 / 右 | 小幅向左 / 向右调整朝向 |
| `X` 或 `Y` | 重新初始化基座四元数，将当前朝向设为零朝向 |
| `F1` | 切换到 Planner 模式；NeuGaze 联调时不要按 |
| `Select` | 立即停止控制并退出 |

### 遥控器：Planner 模式

Planner 模式用于连续行走控制，不是 NeuGaze 参考动作联调的必要步骤。按 `F1` 进入或退出：

| 遥控器输入 | 功能 |
| --- | --- |
| 左摇杆 | 控制移动方向；回到死区时停止移动 |
| 右摇杆左 / 右 | 连续调整面朝方向 |
| `L1` / `R1` | 上一个 / 下一个移动模式 |
| 按住 `L2` / `R2` | 降低 / 提高移动速度；蹲伏模式下调整高度 |
| `A` | 播放或恢复动作 |
| `B` | 立即暂停并回到 Idle |
| `F1` | 返回普通参考动作模式 |
| `Select` | 立即停止控制并退出 |

### 停止功能的区别

实机运行时应始终有人准备使用物理急停，并在 SONIC 终端保留键盘：

- `O`：立即停止控制并退出 SONIC。
- 遥控器 `Select`：立即停止控制并退出 SONIC。
- 遥控器 `B`：停止当前参考动作并回到第 0 帧，但 SONIC 继续运行。
- NeuGaze 的闭左眼“停止”：停止当前参考动作并回到第 0 帧，等价于 reference-motion 模式的 `R`，不是物理急停，也不会退出 SONIC。
- 物理急停：实机安全的最终保障，不能由 NeuGaze、键盘或软件按钮替代。

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
