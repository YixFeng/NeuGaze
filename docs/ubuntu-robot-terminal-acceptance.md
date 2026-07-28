# Ubuntu 机器人终端动作真人验收

本文只适用于 Ubuntu 24.04 Xorg；以下均为待执行的真人验收，不是完成声明。

## 安全范围

- 当前 Ubuntu 路径只向启动 GUI 的 Terminal 打印 `[ROBOT_ACTION]` 或 `[ROBOT_ACTION_CANCELLED]`；没有 SONIC、ZMQ 或实体机器人连接。
- `stop` 只打印 `id=stop`，不是实体机器人的物理急停；SONIC/实体安全链路未开始。
- 只能明确选择 Orbbec SDK 或 OpenCV/V4L2；所选后端失败必须直接报错，不能切换后端。
- 任一失败先保留首次 Terminal 原始输出、截图和时间；不得先调阈值、重启或改配置，再把首次结果倒记为“通过”。

## 启动前确认

在仓库根目录、已从登录界面选择 **Ubuntu on Xorg** 的普通用户会话执行：

```bash
git branch --show-current
printf 'XDG_SESSION_TYPE=%s\nDISPLAY=%s\n' "$XDG_SESSION_TYPE" "$DISPLAY"
lsusb | rg '2bc5:0800|Orbbec|Gemini'
export NEUGAZE_ORBBEC_SDK_ROOT=/home/yixiao/Users/yixiao/Misc/OrbbecSDK_v2
/home/yixiao/miniconda3/envs/neugaze/bin/python scripts/check_ubuntu_install.py --orbbec-sdk-root "$NEUGAZE_ORBBEC_SDK_ROOT" --require-overlay
/home/yixiao/miniconda3/envs/neugaze/bin/python scripts/check_ubuntu_runtime.py --config configs/cpu.yaml --require-overlay
```

预期：分支为 `ubuntu-xorg-port`，`XDG_SESSION_TYPE=x11`、`DISPLAY` 非空，Gemini 335（USB ID `2bc5:0800`）可见，两个只读诊断逐项 `PASS` 且 exit 0。当前 `configs/cpu.yaml` 是 Orbbec SDK 的 Gemini 335 RGB `1280x720 @ 30 FPS`；若已明确选择 OpenCV/V4L2，只确认所选 `/dev/videoN`，不把它当 Orbbec 备用路径。

## 启动、校准和中立观察

```bash
/home/yixiao/miniconda3/envs/neugaze/bin/python config_gui_cpu.py
```

在 GUI 选择 **Orbbec**、选中 Gemini 335（型号/序列号）并确认预览；完成所需校准后点击 **Start Evaluation**。确认按钮变为 **Stop Evaluation**，Camera Setup 里的相机切换与标定按钮禁用，但其他配置标签页仍可点击查看和操作。保持中立表情连续 2 分钟，预期没有任何 `[ROBOT_ACTION]` 或 `[ROBOT_ACTION_CANCELLED]` 行；记录起止时间和实际行数。

## 直接表情：各 5 次

每次恢复中立后再触发；每次只应出现一行。

| 表情（当前配置） | 次数 | 精确预期 Terminal 输出 | 状态 |
|---|---:|---|---|
| 嘟嘴（`mouthPucker`） | 5 | `[ROBOT_ACTION] id=wave label=挥手 source=expression` | 未执行 |
| 抬眉（`browInnerUp`） | 5 | `[ROBOT_ACTION] id=dance label=舞蹈 source=expression` | 未执行 |
| 左眼单眨（`eyeBlinkLeft`，右眼不触发） | 5 | `[ROBOT_ACTION] id=stop label=停止 source=expression` | 未执行 |

## 头部方向控制的透明全屏四分区：各 5 次

每次均按真实身体序列执行：**张嘴并保持以打开透明全屏选择层 → 头部从中立位向目标方向移动并保持 → 闭嘴提交**。确认选择层覆盖整个主屏幕，桌面仍可见，只有对角分区线、四个中文动作标签和当前方向的低透明蓝色高亮；窗口不得抢焦点或拦截点击。当前 `numlock` 由 `jawOpen` 触发；选择只使用 MediaPipe 头姿角，不使用注视坐标。默认俯仰阈值为 `10°`、偏航阈值为 `12°`。前、后、左、右每个方向都完整重复该序列 5 次；每次等待对应输出后再开始下一次。

| 身体动作 / 方向 | 次数 | 精确预期 Terminal 输出 | 状态 |
|---|---:|---|---|
| 抬头 / 前进 | 5 | `[ROBOT_ACTION] id=move_forward_step label=前进一步 source=wheel` | 未执行 |
| 低头 / 后退 | 5 | `[ROBOT_ACTION] id=move_backward_step label=后退一步 source=wheel` | 未执行 |
| 向左转头 / 左转 | 5 | `[ROBOT_ACTION] id=turn_left label=左转 source=wheel` | 未执行 |
| 向右转头 / 右转 | 5 | `[ROBOT_ACTION] id=turn_right label=右转 source=wheel` | 未执行 |

### 无选区取消

张嘴打开选择层后保持头部位于俯仰和偏航阈值以内的中立死区，再闭嘴。预期只出现：

```text
[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel
```

这是取消记录，不是动作成功，也不能伴随任何 `[ROBOT_ACTION]` 行。

### 无系统键鼠副作用

评估前将空白文本编辑器置于可见位置并记下指针位置。执行上述 35 次动作和一次取消时，文本不得出现字符，编辑器不得被点击，指针不得移动，不得滚动或改变窗口焦点。focused 自动化已覆盖 Ubuntu 轮盘打开不移动桌面指针、七个动作不使用桌面输入；真人观察仍须独立记录。

## 退出与资源检查

点击 **Stop Evaluation**（也可按 **ESC+Q**）停止 evaluation；等待按钮恢复为 **Start Evaluation** 后正常关闭 GUI。确认 GUI 已关闭后，再执行：

```bash
pgrep -af 'config_gui_cpu\.py|my_model_arch\.cpu_fast\.pipeline'
lsof -nP | rg 'pyorbbecsdk|libOrbbecSDK|/dev/video'
```

预期两条命令无匹配行（通常 exit 1）。若仍有行，保留完整输出并记失败；不要杀进程后改记通过。

## 本次真人验收记录

| 项目 | 状态（通过/失败/未执行） | 原始证据或备注 |
|---|---|---|
| 启动前 Xorg、分支、Gemini 335 与诊断 | 未执行 | 待真实 Ubuntu Xorg 会话 |
| GUI 预览、校准与 Start Evaluation | 未执行 | 待执行 |
| 中立 2 分钟无输出 | 未执行 | 待执行 |
| 三个直接表情各 5 次 | 未执行 | 待执行 |
| 四方向各 5 次 | 未执行 | 待执行 |
| 无选区取消 | 未执行 | 待执行 |
| 无系统键鼠副作用 | 未执行 | 待执行 |
| ESC+Q 停止 evaluation、正常关闭 GUI 与资源检查 | 未执行 | 待执行 |
| SONIC 接入 | 未开始 | 不在本次范围 |
