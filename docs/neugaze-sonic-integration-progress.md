# NeuGaze × SONIC 集成进度

更新时间：2026-07-29

## 已确认的目标

- NeuGaze 的两个四分区轮盘输出 8 个稳定动作 ID。
- SONIC 从 `gear_sonic_deploy/reference/neugaze_robot_action` 预加载对应的 8 个 reference motion。
- 两个进程通过本机 ZeroMQ `ipc://` 请求/响应通道传递动作 ID，不传输 CSV 或逐帧姿态。
- `闭左眼 -> stop` 必须与用户实际测试的 reference-motion 模式 `R` 完全一致：
  - `operator_state.play = false`
  - `current_frame = 0`
  - `reinitialize_heading = true`
- 上述 `stop` 不是 planner 模式的 momentum reset，也不是设置
  `operator_state.stop = true` 的全局/物理急停。

## 动作映射

| NeuGaze action ID | SONIC reference motion |
|---|---|
| `move_forward_step` | `210707_walk_forward_normal_002__A005` |
| `move_backward_step` | `220720_walk_backward_loop_001__A029` |
| `turn_left` | `220705_Turn_Left_0045_001__A017_M` |
| `turn_right` | `220705_Turn_Right_0045_001__A017_M` |
| `strafe_left` | `220705_Sideway_Walk_Left_001__A017` |
| `strafe_right` | `220713_walk_sideway_right_loop_001__A021` |
| `wave` | `230904_walk_180_wave_180_R_002__A439` |
| `dance` | `230112_lasso_dance_R_001__A116` |

## 协议决定

- transport：ZeroMQ `REQ/REP`
- endpoint：显式配置的 `ipc://` 地址
- `play_action` 只传稳定 `action_id`；动作目录映射由 SONIC 持有并在启动时校验。
- NeuGaze 的 `stop` 转换为协议命令 `reset_reference_motion`。
- 请求失败、超时、未知动作、动作文件缺失均显式报错；不自动重试，不回退到 Terminal 伪成功。

## 当前进度

- [x] 核对 NeuGaze 当前 8 个轮盘动作和 `stop` 动作 ID。
- [x] 核对 SONIC reference-motion 与 planner 模式中 `R` 的不同语义。
- [x] 用户确认实际测试时未进入 planner，采用 reference-motion `R` 语义。
- [x] 确认 SONIC 已依赖 libzmq；已在 `neugaze` conda 环境安装 `pyzmq==27.1.0`。
- [x] SONIC：实现独立动作命令端点、动作映射与启动校验。
- [x] NeuGaze：实现 `terminal` / `sonic_ipc` 显式输出模式。
- [x] 自动化测试：初始集成 NeuGaze 相关回归 211 项通过；SONIC 新测试 2 项通过；SONIC 完整构建通过。
- [x] 用户确认独立 `send_sonic_action.py` 能驱动 MuJoCo，证明 SONIC endpoint 与动作映射可用。
- [x] 修复 evaluation worker 漏传 `robot_action_output_config` 导致配置被隐式当作 Terminal 的问题；移除该隐式默认并完成 247 项相关回归测试。
- [x] SONIC 全量测试入口已检查；既有 `FK.TestFKAndGlobalVelocities` 因仓库缺少 `reference/bones_072925_test/` 测试夹具而无法继续，该问题与本次集成无关。
- [x] 编写 MuJoCo 联调文档和独立动作发送脚本。
- [ ] 用户使用修复后的 evaluation worker 重新完成摄像头真人联调。

## 工作区保护

NeuGaze 中以下内容是用户现有改动，不得覆盖：

- `configs/cpu.yaml` 中已有的本机标定模型路径
- `Log/`

WBC 中以下内容是用户现有改动，不得覆盖：

- `codex_plan/isaacsim_sage3d_scene_hydra.md`（已删除）
- `gear_sonic/config/isaacsim_deploy.yaml`
- `gear_sonic/tests/test_convert_bones_seed.py`
- `gear_sonic_deploy/reference/neugaze_robot_action/`（未跟踪动作数据）
