# Ubuntu 机器人终端动作实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在 Ubuntu 24.04 Xorg 上保留 Gemini 335、面部识别和注视轮盘，把所有键鼠输出替换为七个可在 Terminal 验证的语义化 `RobotAction`；Windows 原键鼠模式保持不变。

**架构：** 新建一个小型 `robot_actions.py`，只负责动作值对象、严格配置校验和同步 Terminal 输出。`RealAction` 在构造时根据显式平台选择互斥的 Windows desktop 路径或 Ubuntu robot-terminal 路径；Ubuntu 直接表情产生一次性动作，轮盘保存原始 `RobotAction` 并在闭嘴时提交。`GazeMouseController` 在机器人模式只把注视坐标写入轮盘状态，绝不调用桌面输入 API。

**技术栈：** Python 3.10、dataclasses、PyYAML、pytest、Tkinter、PySide6、MediaPipe、Ubuntu 24.04 Xorg/X11、Orbbec Gemini 335 RGB。

## 全局约束

- Windows 的 `game`、`game_cs`、`game_wz`、`type` 配置、键盘、鼠标、组合键和轮盘行为不得改变。
- Ubuntu 只有 `robot` 模式，只接受 `RobotAction`，不得产生键盘、鼠标按键、系统指针移动或滚轮事件。
- 第一阶段只打印动作词条；不得连接 SONIC、ZMQ、MuJoCo 或实体机器人。
- 七个动作 ID 固定为 `move_forward_step`、`move_backward_step`、`turn_left`、`turn_right`、`wave`、`dance`、`stop`。
- 直接表情只在 `False -> True` 时输出一次；保持和释放均不输出。
- 张嘴打开四向轮盘，注视选择，闭嘴提交；无有效选区时只打印明确取消信息。
- Ubuntu 轮盘默认半径为 400，四个方向固定为上前进、下后退、左左转、右右转。
- 不新增 manager、factory、插件注册表、自动重试、自动降级或任何 silent fallback。
- 所有原异常和 traceback 必须保留；清理错误只能附加到主异常。
- 当前工作树已有未提交的 `README.md` 修改，所有任务都不得覆盖、暂存或提交它。
- 不需要安装依赖或使用 `sudo`；如果实施中发现必须安装系统包，先停止并请求用户批准。
- 所有 Python 测试使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest ...`。

---

### Task 1：机器人动作契约与严格配置校验

**文件：**
- 新建：`my_model_arch/cpu_fast/robot_actions.py`
- 新建：`tests/test_robot_actions.py`

**接口：**
- 输入：设计文档中的 `robot_action_config` mapping。
- 输出：
  - `RobotAction(action_id: str, label: str, source: Literal["wheel", "expression"])`
  - `validate_robot_action_config(config: Mapping[str, object]) -> dict[str, object]`
  - `resolve_robot_action(config: Mapping[str, object], action_id: str, source: str) -> RobotAction`
  - `emit_robot_action(action: RobotAction, stream: TextIO | None = None) -> None`
  - `emit_robot_action_cancelled(*, reason: str, source: str, stream: TextIO | None = None) -> None`
- 后续任务只使用以上接口，不直接拼接输出字符串。

- [ ] **Step 1：为不可变动作对象和精确输出编写失败测试**

```python
from dataclasses import FrozenInstanceError
from io import StringIO

import pytest

from my_model_arch.cpu_fast.robot_actions import (
    RobotAction,
    emit_robot_action,
    emit_robot_action_cancelled,
)


def test_robot_action_is_immutable_and_prints_one_flushed_line():
    action = RobotAction("move_forward_step", "前进一步", "wheel")
    stream = StringIO()

    emit_robot_action(action, stream=stream)

    assert stream.getvalue() == (
        "[ROBOT_ACTION] id=move_forward_step "
        "label=前进一步 source=wheel\n"
    )
    with pytest.raises(FrozenInstanceError):
        action.label = "changed"


def test_robot_action_cancel_is_explicit():
    stream = StringIO()
    emit_robot_action_cancelled(
        reason="no_selection",
        source="wheel",
        stream=stream,
    )
    assert stream.getvalue() == (
        "[ROBOT_ACTION_CANCELLED] "
        "reason=no_selection source=wheel\n"
    )
```

- [ ] **Step 2：运行动作对象测试并确认 RED**

运行：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py -v
```

预期：collection 失败，`my_model_arch.cpu_fast.robot_actions` 不存在。

- [ ] **Step 3：实现最小动作对象和同步输出**

```python
from dataclasses import dataclass
import sys
from typing import Literal, TextIO


@dataclass(frozen=True, slots=True)
class RobotAction:
    action_id: str
    label: str
    source: Literal["wheel", "expression"]

    def __post_init__(self):
        if not self.action_id:
            raise ValueError("RobotAction.action_id must be non-empty")
        if not self.label:
            raise ValueError("RobotAction.label must be non-empty")
        if self.source not in ("wheel", "expression"):
            raise ValueError(
                "RobotAction.source must be 'wheel' or 'expression'"
            )


def emit_robot_action(action, stream=None):
    if not isinstance(action, RobotAction):
        raise TypeError("emit_robot_action requires RobotAction")
    output = sys.stdout if stream is None else stream
    print(
        f"[ROBOT_ACTION] id={action.action_id} "
        f"label={action.label} source={action.source}",
        file=output,
        flush=True,
    )
```

`emit_robot_action_cancelled` 同样必须校验 `reason` 和 `source` 为非空字符串，并使用一次 `print(..., flush=True)`；不得捕获写入或 flush 异常。

- [ ] **Step 4：为完整配置校验编写失败测试**

使用一个 `VALID_CONFIG` fixture，内容必须精确包含设计中的七个动作和四个表达式映射。参数化覆盖：

```python
@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda c: c.update(extra={}), "robot_action_config.extra"),
        (lambda c: c["actions"].update(wave=""), "actions.wave"),
        (
            lambda c: c["expressions"]["left_click"].update(
                wheel=["wave", "dance"]
            ),
            "expressions.left_click",
        ),
        (
            lambda c: c["expressions"]["numlock"].update(
                wheel=["turn_left"]
            ),
            "expressions.numlock.wheel",
        ),
        (
            lambda c: c["expressions"]["numlock"].update(
                wheel=["turn_left", "turn_left"]
            ),
            "duplicate action id",
        ),
        (
            lambda c: c["expressions"]["extra"].update(
                action="missing"
            ),
            "expressions.extra.action",
        ),
    ],
)
def test_invalid_robot_config_fails_with_field_path(mutate, message):
    config = copy.deepcopy(VALID_CONFIG)
    mutate(config)
    with pytest.raises((TypeError, ValueError), match=message):
        validate_robot_action_config(config)
```

同时验证返回 mapping 是深拷贝：调用后修改输入配置，已经验证的返回值不得变化。

- [ ] **Step 5：运行配置测试并确认 RED**

运行同一个 `tests/test_robot_actions.py -v` 命令。

预期：动作输出测试通过，配置校验与解析接口因尚未定义而失败。

- [ ] **Step 6：实现严格校验和动作解析**

`validate_robot_action_config` 必须：

1. 要求顶层恰好为 `actions`、`expressions`；
2. 要求两个值都是 mapping；
3. 要求 action ID 和标签都是非空字符串；
4. 要求每个 expression mapping 恰好包含 `action` 或 `wheel` 之一；
5. 要求 wheel 是至少两个元素的 list，元素为唯一且存在的 action ID；
6. 返回 `copy.deepcopy(config)`。

`resolve_robot_action` 必须从已验证配置中查找标签，未知 ID 直接抛出包含 ID 的 `ValueError`，然后返回 `RobotAction`。不得返回 `None` 或默认动作。

- [ ] **Step 7：运行 Task 1 全部测试并确认 GREEN**

运行：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py -v
```

预期：全部通过，无 warning。

- [ ] **Step 8：提交 Task 1**

```bash
git add my_model_arch/cpu_fast/robot_actions.py tests/test_robot_actions.py
git diff --cached --check
git commit -m "feat: add robot action contract"
```

---

### Task 2：显式平台路由、Ubuntu 配置和直接表情输出

**文件：**
- 修改：`configs/cpu.yaml:20-32,247-615`
- 修改：`config_gui_cpu.py:995-1020,1395-1460`
- 修改：`my_model_arch/cpu_fast/pipeline.py:2293-2405,2629-2850`
- 修改：`tests/test_config_gui_camera.py:20-130,580-665`
- 修改：`tests/test_pipeline_runtime.py:20-150,820-1090,1640-1670`

**接口：**
- 使用 Task 1 的 `validate_robot_action_config`、`resolve_robot_action`、`emit_robot_action`。
- 扩展构造函数：

```python
RealAction(
    ...,
    robot_action_config=None,
    action_platform=None,
)
```

- `action_platform=None` 时读取 `sys.platform`；测试必须传入 `"linux"` 或 `"win32"`，不能 monkeypatch 全局平台。
- 构造后设置 `self.action_output`，值只能为 `"robot_terminal"` 或 `"desktop"`。
- Ubuntu 使用 `_decode_robot_actions(state_dict: Mapping[str, dict]) -> None`；Windows 继续执行现有 decode 分支。

- [ ] **Step 1：为默认 YAML 的七动作合同编写失败测试**

在 `tests/test_pipeline_runtime.py` 添加：

```python
def test_default_robot_config_has_exact_action_contract():
    mapping = yaml.safe_load(
        (Path(__file__).parents[1] / "configs/cpu.yaml")
        .read_text(encoding="utf-8")
    )
    robot = mapping["robot_action_config"]
    assert robot["actions"] == {
        "move_forward_step": "前进一步",
        "move_backward_step": "后退一步",
        "turn_left": "左转",
        "turn_right": "右转",
        "wave": "挥手",
        "dance": "舞蹈",
        "stop": "停止",
    }
    assert robot["expressions"] == {
        "numlock": {"wheel": [
            "move_forward_step",
            "move_backward_step",
            "turn_left",
            "turn_right",
        ]},
        "left_click": {"action": "wave"},
        "num8": {"action": "dance"},
        "extra": {"action": "stop"},
    }
```

- [ ] **Step 2：运行精确配置测试并确认 RED**

此时还没有 `robot_action_config`，运行：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_pipeline_runtime.py::test_default_robot_config_has_exact_action_contract -v
```

预期：FAIL，`KeyError: 'robot_action_config'`。

- [ ] **Step 3：加入七动作 Ubuntu 配置并确认 GREEN**

将设计文档中的 `robot_action_config` 原样加入 `configs/cpu.yaml`。不要删除或改写 `key_config`。重新运行 Step 2 的单测试命令，预期 PASS。

- [ ] **Step 4：为构造期平台边界编写失败测试**

复用现有禁用真实模型加载的 constructor fixture，分别构造：

```python
linux_pipeline = RealAction(
    action_platform="linux",
    robot_action_config=robot_config,
    configuration=windows_key_config,
    ...,
)
assert linux_pipeline.action_output == "robot_terminal"
assert linux_pipeline.sys_mode == "robot"
assert linux_pipeline.sys_mode_list == ["robot"]

windows_pipeline = RealAction(
    action_platform="win32",
    robot_action_config=robot_config,
    configuration=windows_key_config,
    sys_mode="game_cs",
    ...,
)
assert windows_pipeline.action_output == "desktop"
assert windows_pipeline.sys_mode == "game_cs"
```

另外验证 Linux 缺少 `robot_action_config`、Windows 缺少 `configuration`、未知平台 `darwin` 都在构造期报错。

- [ ] **Step 5：运行平台构造测试并确认 RED**

预期：`RealAction` 尚不接受 `robot_action_config`/`action_platform`，或者 Linux 仍选择旧模式。

- [ ] **Step 6：实现构造期显式平台路由**

在 `RealAction.__init__` 最前面规范化平台：

```python
platform_name = sys.platform if action_platform is None else action_platform
if platform_name == "win32":
    self.action_output = "desktop"
elif platform_name.startswith("linux"):
    self.action_output = "robot_terminal"
else:
    raise RuntimeError(f"unsupported action platform: {platform_name!r}")
```

- desktop 路径继续调用 `get_configuration(configuration)` 并使用传入的 `sys_mode`；
- robot-terminal 路径必须校验并保存 `robot_action_config` 的深拷贝，把 `self.configuration` 设为只含 `robot` 的明确结构、`self.sys_mode="robot"`、`self.sys_mode_list=["robot"]`；
- 禁止在 robot-terminal 路径调用 `get_configuration(None)` 获取默认游戏键位。

更新 `tests/test_pipeline_runtime.py::_real_action_without_constructor()`，显式设置 `pipeline.action_output = "desktop"`，避免对象绕过构造后隐式猜平台。

- [ ] **Step 7：为直接表情的一次性输出编写失败测试**

构造最小 `state_dict`，依次模拟 `FT`、`TT`、`TF`。对 `left_click`、`num8`、`extra` 参数化：

```python
@pytest.mark.parametrize(
    ("expression_id", "expected_id", "expected_label"),
    [
        ("left_click", "wave", "挥手"),
        ("num8", "dance", "舞蹈"),
        ("extra", "stop", "停止"),
    ],
)
def test_robot_direct_expression_emits_once_on_rising_edge(
    capsys, expression_id, expected_id, expected_label
):
    pipeline = robot_pipeline_without_constructor()
    pipeline.keys_dict = SimpleNamespace(state_dict={
        expression_id: transition("FT", value=True),
    })
    pipeline.head_dict = SimpleNamespace(state_dict={})

    pipeline.decode()
    pipeline.keys_dict.state_dict[expression_id] = transition(
        "TT", value=True
    )
    pipeline.decode()
    pipeline.keys_dict.state_dict[expression_id] = transition(
        "TF", value=False
    )
    pipeline.decode()

    assert capsys.readouterr().out == (
        f"[ROBOT_ACTION] id={expected_id} "
        f"label={expected_label} source=expression\n"
    )
```

同时验证未配置的 `num1` 即使 `FT` 也不输出。

- [ ] **Step 8：运行直接表情测试并确认 RED**

预期：现有 `decode()` 仍把动作解释为键位，或者没有 robot decoder。

- [ ] **Step 9：实现 Ubuntu 直接表情 decoder 和互斥输出边界**

`decode()` 第一层只分派一次：

```python
state_dict = combine_dicts(...)
if self.action_output == "robot_terminal":
    self._decode_robot_actions(state_dict)
    return
self._decode_desktop_actions(state_dict)
```

把现有 Windows decode 主体原样移入 `_decode_desktop_actions`，不要在其中加入 Linux 特例。

`_decode_robot_actions` 只遍历 `robot_action_config["expressions"]`；直接动作只接受 `state["diff"] is True` 且 `state["cp"] == "FT"`。使用 `resolve_robot_action(..., source="expression")` 后同步调用 `_execute_action`。

`_execute_action_once` 必须先检查平台边界：

```python
if self.action_output == "robot_terminal":
    if not isinstance(action, RobotAction):
        raise TypeError("Ubuntu robot output requires RobotAction")
    emit_robot_action(action)
    return
if isinstance(action, RobotAction):
    raise TypeError("Windows desktop output rejects RobotAction")
```

然后执行原 desktop 逻辑。不要保留原来对 robot 动作可能返回 `None` 的入口。

- [ ] **Step 10：让 GUI 注入并无损保存机器人配置**

在 `ConfigWindow.initialize_pipeline()` 增加：

```python
robot_action_config=self.config.get("robot_action_config")
```

`save_config_to_file()` 已从 `copy.deepcopy(self.config)` 开始，因此不得新建机器人动作编辑器；只增加 roundtrip 测试，确认保存摄像头或其他字段后 `robot_action_config` 字节语义对应的 mapping 完全不变。

- [ ] **Step 11：运行 Task 2 focused 测试并确认 GREEN**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py tests/test_pipeline_runtime.py tests/test_config_gui_camera.py -v
```

预期：全部通过；Windows action/lifecycle 现有测试无回归。

- [ ] **Step 12：提交 Task 2**

```bash
git add configs/cpu.yaml config_gui_cpu.py my_model_arch/cpu_fast/pipeline.py tests/test_config_gui_camera.py tests/test_pipeline_runtime.py
git diff --cached --check
git commit -m "feat: route Ubuntu expressions to robot actions"
```

---

### Task 3：四方向 RobotAction 轮盘、坐标转换和取消语义

**文件：**
- 修改：`my_model_arch/cpu_fast/pipeline.py:2847-3120`
- 修改：`tests/test_pipeline_runtime.py:390-435,1320-1470`

**接口：**
- `SectorWheel` 新增：
  - `_category_label(category: object) -> str`
  - `_screen_to_canvas(screen_x: float, screen_y: float) -> tuple[float, float]`
  - `get_cardinal_from_mouse_position(event) -> int | None`
  - `draw_cardinal(highlighted_sector: int | None = None) -> None`
- robot wheel category 保留完整 `RobotAction`，只在绘制文字时读取 `.label`。
- `RealAction.make_wheel_action(selected: object) -> Action | RobotAction | None` 是 `ObserverWithSectorWheel` 提交选区的唯一入口。

- [ ] **Step 1：为四方向空间映射编写失败测试**

不启动 Tk 主循环，使用 `object.__new__(SectorWheel)` 和带宽高的 fake canvas。半径 400、中心 `(400, 400)` 时验证：

```python
@pytest.mark.parametrize(
    ("point", "expected_index"),
    [
        ((400, 100), 0),   # 前进一步
        ((400, 700), 1),   # 后退一步
        ((100, 400), 2),   # 左转
        ((700, 400), 3),   # 右转
        ((0, 0), None),    # 圆外
    ],
)
def test_cardinal_wheel_maps_fixed_directions(point, expected_index):
    wheel = cardinal_wheel_without_tk(radius=400)
    event = SimpleNamespace(x=point[0], y=point[1])
    assert wheel.get_cardinal_from_mouse_position(event) == expected_index
```

还要验证轴线相等时的确定规则：垂直优先；中心点返回 `None`，防止无注视方向时默认前进。

- [ ] **Step 2：运行四方向测试并确认 RED**

预期：`get_cardinal_from_mouse_position` 不存在。

- [ ] **Step 3：实现 `cardinal` 布局和 RobotAction 标签绘制**

`update_categories` 接受 `layout_type="cardinal"`，并严格要求四个 category；否则抛出 `ValueError`。

选择算法直接比较中心偏移，不经过角度取整：

```python
dx = event.x - self.radius
dy = event.y - self.radius
if dx == 0 and dy == 0:
    return None
if dx * dx + dy * dy > self.radius * self.radius:
    return None
if abs(dy) >= abs(dx):
    return 0 if dy < 0 else 1
return 2 if dx < 0 else 3
```

`draw_cardinal` 使用显式的上、下、左、右 arc 和文字位置；选中项浅灰、未选中项白色。`_category_label` 对 `RobotAction` 返回 `.label`，对 Windows 字符串返回 `str(category)`，不得修改存储在 `selected_sector` 中的原对象。

- [ ] **Step 4：为屏幕坐标转换编写失败测试**

fake `messagebox.winfo_rootx()` 返回 560，`winfo_rooty()` 返回 140。验证屏幕点 `(960, 540)` 转为 Canvas 中心 `(400, 400)`；再以 3072×1920 屏幕的非零窗口原点验证四个方向。窗口 origin 查询抛出的原异常必须传播。

- [ ] **Step 5：实现显式 screen-to-canvas 转换**

`check_op_xy()` 在构造事件前执行：

```python
local_x, local_y = self._screen_to_canvas(*self.subject.op_xy)
event.x = local_x
event.y = local_y
```

`_screen_to_canvas` 只做减法，不 clip、不捕获 Tk 错误、不猜测窗口位置。

- [ ] **Step 6：为 robot 轮盘打开、提交和取消编写失败测试**

覆盖以下行为：

1. `numlock FT` 将四个 `RobotAction(source="wheel")` 写入 `wheel_categories`，设置 `wheel_layout_type="cardinal"`；
2. robot 轮盘打开时不得调用 `desktop.move_pointer`；
3. Windows 轮盘打开仍把指针移动到屏幕中心；
4. robot 选中 `turn_left` 并闭嘴时，队列中是同一个 `RobotAction`，drain 后打印一次；
5. robot 无选区闭嘴时，不入队并精确打印取消行；
6. Windows 选中字符串时仍产生原 `Action(..., OpType.KEYPRESS)`。

- [ ] **Step 7：运行轮盘行为测试并确认 RED**

预期：当前 observer 始终移动系统指针，并把所有选区转换为键盘 `Action`。

- [ ] **Step 8：实现平台感知但不回退的轮盘提交**

- robot decoder 在 `numlock FT` 时解析并保存四个 `RobotAction`；
- `ObserverWithSectorWheel` 只在 `subject.action_output == "desktop"` 时居中系统指针；
- observer 闭轮盘时调用 `subject.make_wheel_action(selected)`；
- robot 无选区时 `make_wheel_action` 调用 `emit_robot_action_cancelled(...)` 并返回 `None`；
- robot 有选区但类型不是 `RobotAction` 时抛 `TypeError`；
- desktop 路径保持原 `Action(str(selected), OpType.KEYPRESS)` 语义。

轮盘对象保持原异常监督、stop/join 和 action queue 边界，不创建第二个 worker。

- [ ] **Step 9：运行 Task 3 focused 测试并确认 GREEN**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py tests/test_pipeline_runtime.py -v
```

预期：全部通过，无残留 wheel thread warning。

- [ ] **Step 10：提交 Task 3**

```bash
git add my_model_arch/cpu_fast/pipeline.py tests/test_pipeline_runtime.py
git diff --cached --check
git commit -m "feat: add gaze-selected robot action wheel"
```

---

### Task 4：机器人模式仅内部传递注视，证明零桌面输入

**文件：**
- 修改：`my_model_arch/cpu_fast/eye_gaze_mouse_control.py:20-250`
- 修改：`my_model_arch/cpu_fast/pipeline.py:1360-1410,2180-2240,2293-2350,2720-2755`
- 修改：`tests/test_gaze_mouse_controller.py:1-220`
- 修改：`tests/test_pipeline_runtime.py:820-1090,1560-1620`

**接口：**
- 扩展构造函数：

```python
GazeMouseController(
    ...,
    desktop_pointer_control: bool = True,
)
```

- `desktop_pointer_control=True` 完整保留 Windows 行为。
- `desktop_pointer_control=False` 时：轮盘隐藏则丢弃该帧注视控制请求；轮盘显示则只更新 `observer.op_xy=(x, y)`。
- `RealAction` 在 `robot_terminal` 路径强制传入 `desktop_pointer_control=False`、`select_wheel_using_head=False`；调用者不得通过 YAML 把它重新打开。
- `RealAction.move_mouse()` 在 robot-terminal 路径只把 `predicted_position` 写成供轮盘使用的 `mouse_dict["x"]`/`["y"]`，不得查询系统指针。
- pipeline 的 `uses_desktop_input` 在普通/Windows 路径为 `True`，在 Ubuntu robot-terminal 路径为 `False`；退出时只有前者调用 `desktop.release_all()`。

- [ ] **Step 1：为机器人凝视控制编写失败测试**

把下列 desktop 函数全部替换为立即失败：

```python
for name in (
    "get_pointer_position",
    "move_pointer",
    "key_down",
    "key_up",
    "key_up_owned",
    "scroll",
    "release_all",
):
    monkeypatch.setattr(
        desktop,
        name,
        lambda *args, name=name, **kwargs: pytest.fail(
            f"robot mode called desktop.{name}"
        ),
    )
```

验证：

- wheel hidden 时 robot controller 不改变 `op_xy`；
- wheel visible 时只把 `op_xy` 改为输入的 `(x, y)`；
- worker loop 在 robot 模式不调用 `is_cursor_visible`；
- 超出屏幕的 gaze 值不在 controller 中 clip，保留给轮盘的圆外判断；
- `RealAction.move_mouse()` 不调用 `get_pointer_position`；
- robot pipeline 退出不调用 `release_all`。

- [ ] **Step 2：运行机器人凝视和退出测试并确认 RED**

预期：当前 controller 查询光标可见性并可能移动鼠标，`BindKeys.move_mouse()` 查询系统指针，退出路径无条件调用 `desktop.release_all()`。

- [ ] **Step 3：实现互斥的 controller 分支**

在 `_control_loop` 取到最新 gaze 后先分派：

```python
if not self.desktop_pointer_control:
    if not self.observer.wheel.is_hidden:
        self.observer.op_xy = (gaze_x, gaze_y)
    time.sleep(0.01)
    continue
```

只有 `desktop_pointer_control=True` 才能执行 `is_cursor_visible`、`_handle_visible_cursor` 或 `_handle_invisible_cursor`。不要通过 try/except 把桌面错误改成 robot 行为。

- [ ] **Step 4：为 `RealAction` 强制参数和内部 gaze 数据编写失败测试**

monkeypatch `GazeMouseController` 为记录构造参数的 fake，验证：

```python
assert linux_kwargs["desktop_pointer_control"] is False
assert linux_kwargs["select_wheel_using_head"] is False
assert windows_kwargs.get("desktop_pointer_control", True) is True
```

再给 robot `RealAction.predicted_position=(321, 123)`，把 `desktop.get_pointer_position` 替换成 fail-on-call，调用 `move_mouse()` 后断言：

```python
assert pipeline.mouse_dict == {"x": 321, "y": 123}
```

如果 `mouse_control_config` 在 Linux 配置中显式写入相反值，构造必须报冲突错误，不能悄悄覆盖用户配置或打开桌面输入。

- [ ] **Step 5：实现 `RealAction` 的强制参数、内部 gaze 和退出边界**

复制 `mouse_control_config` 后检查保留字段：

- robot-terminal：缺省时写入两个 `False`；配置若提供非 `False` 值则抛出带字段名的 `ValueError`；
- desktop：原样传给 controller。

覆盖 `RealAction.move_mouse()`：robot-terminal 只复制 `predicted_position` 的 `x/y`；desktop 调用 `super().move_mouse()`。不得修改调用者传入的原 mapping。

在共享 pipeline 初始化中设置 `self.uses_desktop_input=True`。`RealAction` 构造完成平台选择后，仅在 robot-terminal 路径把它设为 `False`。`quit_pipeline()` 使用显式条件：

```python
if self.uses_desktop_input:
    cleanup("desktop.release_all", desktop.release_all)
```

属性缺失必须视为编程错误，不能用 `getattr(..., True)` 隐式猜测；所有绕过构造的测试 helper 都要显式设置该属性。

- [ ] **Step 6：执行完整 robot 识别到输出的无桌面事件测试**

在一个测试中依次触发 `wave`、`dance`、`stop` 和四个 wheel action，然后执行正常退出；保持所有 desktop 写入/状态变更函数为 fail-on-call。断言 Terminal 恰好得到七条 `[ROBOT_ACTION]`，没有键鼠调用，没有 `release_all`，没有重复输出。

- [ ] **Step 7：运行 controller、pipeline 和 Windows action 回归**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_keyboard_actions.py tests/test_desktop_selection.py -v
```

预期：全部通过；现有 Windows/desktop controller 测试保持原断言，Windows 退出仍执行一次 `release_all`。

- [ ] **Step 8：提交 Task 4**

```bash
git add my_model_arch/cpu_fast/eye_gaze_mouse_control.py my_model_arch/cpu_fast/pipeline.py tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py
git diff --cached --check
git commit -m "fix: isolate robot gaze from desktop input"
```

---

### Task 5：中文实测文档、进度记录和全分支验证

**文件：**
- 新建：`docs/ubuntu-robot-terminal-acceptance.md`
- 修改：`docs/ubuntu-xorg-port-progress.md`
- 测试：`tests/test_robot_actions.py`
- 测试：`tests/test_pipeline_runtime.py`
- 测试：`tests/test_gaze_mouse_controller.py`
- 测试：`tests/test_config_gui_camera.py`
- 测试：现有全部 `tests/`

**接口：**
- 不新增运行时接口。
- 验收文档只覆盖 Ubuntu，不写 Windows 操作，不声称真人验收已通过。

- [ ] **Step 1：写中文实际验收文档**

文档必须包含：

1. 启动前确认 Ubuntu Xorg、Gemini 335、当前分支和依赖诊断的命令；
2. 启动 GUI/评估管线的仓库真实命令；
3. 中立表情两分钟观察；
4. 嘟嘴、抬眉、左眼单眨各 5 次；
5. 前进、后退、左转、右转各 5 次；
6. 每条预期 Terminal 输出；
7. 无选区取消测试；
8. 用可观察方式确认没有系统键鼠事件；
9. ESC+Q/正常退出后的资源检查命令；
10. 逐项的“通过/失败/未执行”记录表。

文档必须明确：当前只打印，不连接 SONIC；`stop` 不是实体机器人的物理急停；任何失败先保存原日志，不能先调阈值后把首次结果记为通过。

- [ ] **Step 2：更新协作进度文档**

在 `docs/ubuntu-xorg-port-progress.md` 增加独立的“Ubuntu robot terminal actions”阶段，记录：

- 设计提交 `7a8f897` 和中文提交 `3998fe6`；
- 每个实施任务提交；
- focused/full 测试命令和精确结果；
- 真人验收仍为“未执行”；
- SONIC 接入仍为“未开始”。

不得改写既有历史测试证据。

- [ ] **Step 3：运行 focused 自动测试**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest tests/test_robot_actions.py tests/test_pipeline_runtime.py tests/test_gaze_mouse_controller.py tests/test_keyboard_actions.py tests/test_desktop_selection.py tests/test_config_gui_camera.py -v
```

预期：全部通过，无 warning、无 unhandled thread exception。

- [ ] **Step 4：运行完整 non-X11 测试**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m 'not x11' -v
```

预期：全部适用测试通过；仅显式标记的 X11/硬件测试 deselected。

- [ ] **Step 5：运行隔离 Xvfb 测试**

无 compositor：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 xvfb-run -a /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m x11 -v
```

有 compositor：

```bash
xvfb-run -a sh -c 'xcompmgr -a & PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/yixiao/miniconda3/envs/neugaze/bin/python -m pytest -m x11 -v'
```

预期：无 compositor 的透明层负向门禁按既有断言工作；有 compositor 的正向测试通过。不要把 expected skip 记成通过。

- [ ] **Step 6：运行编译、配置和范围门禁**

```bash
/home/yixiao/miniconda3/envs/neugaze/bin/python -m py_compile my_model_arch/cpu_fast/robot_actions.py my_model_arch/cpu_fast/eye_gaze_mouse_control.py my_model_arch/cpu_fast/pipeline.py config_gui_cpu.py tests/test_robot_actions.py tests/test_gaze_mouse_controller.py tests/test_pipeline_runtime.py tests/test_config_gui_camera.py
git diff --check
git status --short
git diff --name-only origin/ubuntu-xorg-port...HEAD
```

检查：

- 没有 `.orig`、`.rej`、临时 Log 或缓存文件；
- `README.md` 仍只保留用户原有未提交修改，没有被本任务 stage；
- 没有新增 SONIC/ZMQ/机器人依赖；
- 没有修改 Windows requirements。

- [ ] **Step 7：只提交文档和最终测试记录**

```bash
git add docs/ubuntu-robot-terminal-acceptance.md docs/ubuntu-xorg-port-progress.md
git diff --cached --check
git commit -m "docs: add Ubuntu robot action acceptance"
```

- [ ] **Step 8：最终状态检查**

```bash
git log --oneline --decorate -8
git status --short --branch
```

预期：功能与文档提交均在 `ubuntu-xorg-port` 独立分支；工作树仅可能保留任务开始前已有的 `README.md` 修改。不要在真人验收前把“识别和轮盘可用”标成完成，也不要开始 SONIC 接入。
