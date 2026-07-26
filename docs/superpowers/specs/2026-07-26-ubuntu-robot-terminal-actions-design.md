# Ubuntu 机器人终端动作设计

## 目标

将 NeuGaze 在 Ubuntu 上的键盘和鼠标动作输出，替换为小而明确的机器人语义动作链路。在连接任何机器人控制器之前，先通过 Terminal 输出验证识别是否正确。

第一阶段验证以下链路：

```text
Gemini 335 RGB
→ 面部表情识别
→ 直接动作或注视轮盘动作
→ RobotAction
→ Terminal 单行输出
```

Windows 保留现有的 `game`、`game_cs`、`game_wz` 和 `type` 模式，以及原有键盘和鼠标行为。Ubuntu 只保留一个 `robot` 模式，并且不得产生键盘、鼠标按键、鼠标移动或滚轮事件。

## 范围

本阶段包括：

- Ubuntu 独立的机器人动作配置；
- 第一批七个机器人动作词条；
- 一次性 Terminal 输出；
- 使用注视位置选择的四方向轮盘；
- 移除 Ubuntu 的桌面输入输出；
- 修正轮盘屏幕坐标到窗口局部坐标的转换；
- 自动化回归测试和实际验收步骤文档。

本阶段不连接 SONIC，不选择 reference motion 目录，不启动控制器，不发送 ZMQ 数据，也不控制仿真或实体机器人。只有实际表情识别和轮盘验收通过后，才能单独设计这些功能。

## 平台边界

两个平台的输出路径必须显式区分且互斥。

Windows：

```text
识别 → 现有键位配置 → Action → 桌面输入后端
```

Ubuntu：

```text
识别 → 机器人动作配置 → RobotAction → Terminal
```

Windows 输出端只接受现有的键盘/鼠标 `Action`。Ubuntu 输出端只接受 `RobotAction`。任一输出端收到错误的动作类型都必须报错。机器人输出不得回退到桌面输入，桌面输入也不得回退到机器人输出。

Ubuntu 仍要求使用 Xorg 来显示 GUI、轮盘和凝视覆盖层，但 `robot` 模式不得通过 Xorg 注入输入事件。

## RobotAction 数据模型

只新增一个不可变的数据对象：

```text
RobotAction(
    action_id="move_forward_step",
    label="前进一步",
    source="wheel",
)
```

- `action_id`：稳定的机器动作标识；
- `label`：轮盘和 Terminal 显示的中文词条；
- `source`：只能是 `wheel` 或 `expression`。

Terminal 输出使用一个直接函数，不引入 manager、factory、插件注册表、传输抽象或后台线程。每个动作打印并立即刷新一行：

```text
[ROBOT_ACTION] id=move_forward_step label=前进一步 source=wheel
```

这个数据对象也是未来的 SONIC 接入边界。后续可以把 `action_id` 映射到 reference motion 目录，而不再修改识别和轮盘选择链路。

## Ubuntu 配置

Ubuntu 不复用 `keyname`、`KEYPRESS` 或 Windows 的四个模式，而是使用独立配置：

```yaml
robot_action_config:
  actions:
    move_forward_step: 前进一步
    move_backward_step: 后退一步
    turn_left: 左转
    turn_right: 右转
    wave: 挥手
    dance: 舞蹈
    stop: 停止

  expressions:
    numlock:
      wheel:
        - move_forward_step
        - move_backward_step
        - turn_left
        - turn_right
    left_click:
      action: wave
    num8:
      action: dance
    extra:
      action: stop
```

继续使用现有的表情识别 ID，第一阶段不修改表情识别算法：

| 识别 ID | 面部动作 | Ubuntu 行为 |
|---|---|---|
| `numlock` | 张嘴并保持 | 打开四动作轮盘 |
| `left_click` | 嘟嘴 | 输出 `wave` |
| `num8` | 抬起内眉 | 输出 `dance` |
| `extra` | 仅眨左眼、右眼保持睁开 | 输出 `stop` |

其他已经识别出的表情和头部动作 ID 在 Ubuntu `robot` 模式中不配置动作。它们仍然是识别数据，但不会产生输出。

在实时管线启动前一次性验证配置：

- 每个被引用的动作 ID 都必须存在于 `actions`；
- 每个中文标签都必须是非空字符串；
- 一个表情必须且只能配置 `action` 或 `wheel` 之一；
- 一个轮盘至少包含两个有效动作 ID；
- 同一个轮盘内不得包含重复动作 ID；
- 机器人动作配置自有结构中的未知字段必须报错。

非法配置必须抛出包含错误字段路径的异常。不得忽略、改写、重试，也不得转换成旧键盘动作。

## 触发语义

直接表情动作采用一次性触发：

- 只在识别状态从 `False → True` 时输出；
- 表情保持为 `True` 时不得重复输出；
- 状态从 `True → False` 时不得输出。

轮盘采用松开确认：

1. `numlock` 从 false 变为 true；
2. 保持张嘴期间显示轮盘；
3. 注视位置更新高亮区域；
4. 闭嘴；
5. 输出一次当前选中的 `RobotAction`，然后关闭轮盘。

关闭轮盘时没有有效选区属于可预期、可观察的取消操作，不是机器人动作：

```text
[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel
```

取消操作不得修改动作状态，也不得自动选择默认区域。

## 轮盘布局和注视选择

Ubuntu 机器人轮盘为屏幕居中、无边框、半透明、始终置顶的 `800 × 800` 窗口，默认半径为 400 像素。Windows 保留当前轮盘配置和行为。

Ubuntu 四个区域的空间含义固定为：

```text
          前进一步

左转                    右转

          后退一步
```

Ubuntu `robot` 模式使用注视位置选择，不使用头部角度。注视坐标只在 NeuGaze 内部传递，不得移动 Xorg 系统指针。

当前代码把屏幕坐标直接交给需要 Canvas 局部坐标的选区逻辑。Ubuntu 实现必须进行显式转换：

```text
local_x = gaze_screen_x - wheel_screen_left
local_y = gaze_screen_y - wheel_screen_top
```

选区必须使用转换后的局部坐标计算。轮盘外的注视点不对应任何选区，不得通过坐标截断把轮盘外位置变成有效选择。

## 错误和清理行为

整条链路遵循可调试性优先原则：

- Ubuntu 机器人输出收到旧桌面 `Action` 时必须报错；
- Windows 桌面输出收到 `RobotAction` 时必须报错；
- 未知动作 ID 必须报错；
- Terminal 写入或刷新失败时保留并抛出原始异常；
- 轮盘线程失败时，在主管线中使用原 traceback 重新抛出；
- 清理过程必须保留主异常，并将清理失败附加到主异常；
- 任何错误都不得触发自动重试、桌面输入回退、缓存输出或伪成功输出。

未配置动作的识别 ID 不属于错误，因为 Ubuntu 动作配置显式决定启用哪些识别通道。

`stop` 在本阶段仅用于验证输出。真实机器人不得把面部识别当作唯一紧急停止机制；后续实体机器人测试必须保留物理急停。

## 自动化验证

测试必须验证真实行为，不能只验证 mock 调用次数：

1. 七个动作 ID 必须解析为精确的中文标签；
2. 每种非法配置必须失败，并指出相关字段路径；
3. 每个直接表情只能在激活时输出一次；
4. 保持和释放直接表情不得继续输出；
5. 上、下、左、右四个注视位置必须选择规定的动作；
6. 非正方形屏幕以及轮盘窗口左上角不为零时，坐标转换仍然正确；
7. 注视点位于轮盘外并关闭轮盘时，只输出取消信息；
8. Ubuntu 测试把所有桌面输入函数替换成“一旦调用就失败”的函数，证明没有键盘、鼠标按键、指针移动或滚轮操作；
9. 动作被发送到错误的平台输出边界时必须明确失败；
10. Windows 现有键盘、鼠标、组合键、轮盘和清理测试必须继续通过；
11. 最终源码状态必须通过适用的完整 Ubuntu 测试、编译和静态检查。

## Ubuntu 实际验收

实际验收在 Ubuntu Xorg 会话中使用已连接的 Gemini 335，并保留原始 Terminal 输出。

1. 保持中立表情两分钟，记录任何误触发；
2. 嘟嘴、抬眉和仅眨左眼分别独立测试 5 次；
3. 确认每次激活只打印一行正确动作；
4. 确认保持和释放每个直接表情时不增加输出；
5. 四个轮盘区域各选择 5 次，共进行 20 次选择；
6. 确认每次选择的高亮区域、空间方向、动作 ID 和中文标签完全一致；
7. 确认保持张嘴不会重复打开轮盘或输出动作；
8. 在没有有效选区时关闭轮盘，确认打印明确的取消信息；
9. 确认系统指针不移动，也不产生按键、鼠标点击或滚轮事件；
10. 退出后确认摄像头、轮盘线程、覆盖层和 NeuGaze 进程全部结束。

任何失败都必须保留为失败并记录原始日志。表情阈值或坐标调整只能基于真实观测结果，并重新执行相同的验收流程。

## 后续 SONIC 接入

实际验收通过后，另行设计以下链路：

```text
RobotAction.action_id
→ 已验证的 reference motion 目录
→ SONIC 动作选择/播放接口
→ MuJoCo 仿真
→ 实体机器人
```

GR00T WholeBodyControl 以独立动作目录加载 reference motion，并支持在 reference-motion 模式中选择和播放已加载动作：

- <https://github.com/NVlabs/GR00T-WholeBodyControl>
- <https://nvlabs.github.io/GR00T-WholeBodyControl/references/motion_reference.html>

后续阶段必须使用稳定动作 ID，而不是中文显示标签；所有 reference motion 必须先在 MuJoCo 中测试；必须保留物理急停；在向实体机器人发送任何命令之前，必须明确 SONIC 的进程和通信边界。
