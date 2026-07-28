import copy
from dataclasses import FrozenInstanceError
from io import StringIO
from pathlib import Path

import pytest

from my_model_arch.cpu_fast.robot_actions import (
    RobotAction,
    emit_robot_action,
    emit_robot_action_cancelled,
)
from my_model_arch.cpu_fast import robot_actions


VALID_CONFIG = {
    "actions": {
        "move_forward_step": "前进",
        "move_backward_step": "后退",
        "turn_left": "左转",
        "turn_right": "右转",
        "strafe_left": "向左横移",
        "strafe_right": "向右横移",
        "wave": "挥手",
        "dance": "舞蹈",
        "stop": "停止",
    },
    "expressions": {
        "numlock": {
            "wheel": [
                "move_forward_step",
                "move_backward_step",
                "turn_left",
                "turn_right",
            ],
        },
        "left_click": {"action": "wave"},
        "num8": {
            "wheel": [
                "wave",
                "dance",
                "strafe_left",
                "strafe_right",
            ]
        },
        "extra": {"action": "stop"},
    },
}


@pytest.fixture
def valid_config():
    return copy.deepcopy(VALID_CONFIG)


def test_robot_action_is_immutable_and_prints_one_flushed_line():
    action = RobotAction("move_forward_step", "前进", "wheel")
    stream = StringIO()

    emit_robot_action(action, stream=stream)

    assert stream.getvalue() == (
        "[ROBOT_ACTION] id=move_forward_step "
        "label=前进 source=wheel\n"
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


@pytest.mark.parametrize("failure_phase", ["write", "flush"])
def test_robot_action_output_preserves_stream_failure_identity(failure_phase):
    error = OSError(f"{failure_phase} failed")

    class FailingStream:
        def write(self, text):
            if failure_phase == "write":
                raise error
            return len(text)

        def flush(self):
            if failure_phase == "flush":
                raise error

    with pytest.raises(OSError) as caught:
        emit_robot_action(
            RobotAction("wave", "挥手", "expression"),
            stream=FailingStream(),
        )

    assert caught.value is error


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
                wheel=[
                    "turn_left",
                    "turn_left",
                    "turn_right",
                    "wave",
                ]
            ),
            "duplicate action id",
        ),
        (
            lambda c: c["expressions"]["extra"].update(action="missing"),
            "expressions.extra.action",
        ),
    ],
)
def test_invalid_robot_config_fails_with_field_path(
    valid_config, mutate, message
):
    mutate(valid_config)

    with pytest.raises((TypeError, ValueError), match=message):
        robot_actions.validate_robot_action_config(valid_config)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda c: c["actions"].update(extra_action="额外动作"),
            "actions.extra_action",
        ),
        (lambda c: c["actions"].pop("stop"), "actions.stop"),
    ],
)
def test_robot_config_requires_exact_fixed_action_ids(
    valid_config, mutate, message
):
    mutate(valid_config)

    with pytest.raises(ValueError, match=message):
        robot_actions.validate_robot_action_config(valid_config)


@pytest.mark.parametrize("wheel_size", [2, 3, 5])
def test_robot_config_requires_exactly_four_wheel_actions(
    valid_config, wheel_size
):
    valid_config["expressions"]["numlock"]["wheel"] = list(
        valid_config["actions"]
    )[:wheel_size]

    with pytest.raises(
        ValueError,
        match=r"expressions\.numlock\.wheel",
    ):
        robot_actions.validate_robot_action_config(valid_config)


def test_validated_robot_config_is_a_deep_copy(valid_config):
    validated = robot_actions.validate_robot_action_config(valid_config)
    valid_config["actions"]["wave"] = "changed"
    valid_config["expressions"]["numlock"]["wheel"].append("wave")

    assert validated["actions"]["wave"] == "挥手"
    assert validated["expressions"]["numlock"]["wheel"] == [
        "move_forward_step",
        "move_backward_step",
        "turn_left",
        "turn_right",
    ]


def test_resolve_robot_action_returns_label_and_rejects_unknown_id(valid_config):
    action = robot_actions.resolve_robot_action(
        valid_config, "wave", "expression"
    )

    assert action == RobotAction("wave", "挥手", "expression")
    with pytest.raises(ValueError, match="missing"):
        robot_actions.resolve_robot_action(valid_config, "missing", "wheel")


@pytest.mark.parametrize(
    ("filename", "required_rows", "obsolete_rows"),
    [
        (
            "README-CN.md",
            (
                "方向必须连续稳定 5 个有效处理帧",
                "第一次张嘴只负责打开轮盘",
                "转头选择期间不需要持续张嘴",
                "回到阈值内的中立死区并保持闭嘴",
                "再次张嘴连续 5 个有效帧",
                "转头选择期间不需要持续抬眉",
                "再次抬眉连续 5 个有效帧",
                "人脸或 blendshape 丢失不会提交",
            ),
            (
                "保持目标方向并闭嘴确认",
                "中立死区会清除选区",
                "同时继续张嘴",
                "连续 5 个有效帧识别为闭嘴",
                "连续 3 个有效帧保持抬眉",
                "连续 5 个有效帧放松眉毛",
            ),
        ),
        (
            "README.md",
            (
                "stable for 5 valid processing frames",
                "This first activation only opens the wheel",
                "You do not need to keep your mouth open while selecting",
                "Open your mouth again while centered",
                "you do not need to keep the brows raised while selecting",
                "raise them again for 5 valid frames",
                "Loss of the face or blendshapes never submits",
            ),
            (
                "Hold the target direction and close your mouth to confirm",
                "Returning to the neutral dead zone clears the selection",
                "while keeping your mouth open",
                "after 5 valid closed-mouth frames",
                "keep the brows raised for 3 valid frames",
                "relax them for 5 valid frames",
            ),
        ),
    ],
)
def test_readmes_document_repeated_expression_confirmation(
    filename, required_rows, obsolete_rows
):
    text = (Path(__file__).parents[1] / filename).read_text(
        encoding="utf-8"
    )

    for row in required_rows:
        assert row in text
    for row in obsolete_rows:
        assert row not in text


@pytest.mark.parametrize(
    ("filename", "expression_rows", "wheel_rows", "obsolete_rows"),
    [
        (
            "README-CN.md",
            (
                "| **张嘴** | `jawOpen > 0.4`",
                "| **嘟嘴** | `mouthPucker > 0.97`",
                "| **抬内眉** | `browInnerUp > 0.8`",
                "| **仅闭左眼** | `eyeBlinkLeft > 0.6`",
            ),
            (
                "| **抬头** | `move_forward_step` | **前进** |",
                "| **低头** | `move_backward_step` | **后退** |",
                "| **向左转头** | `turn_left` | **左转** |",
                "| **向右转头** | `turn_right` | **右转** |",
                "| **抬头** | `wave` | **挥手** |",
                "| **低头** | `dance` | **舞蹈** |",
                "| **向左转头** | `strafe_left` | **向左横移** |",
                "| **向右转头** | `strafe_right` | **向右横移** |",
            ),
            (
                "鼠标左键点击",
                "W/S键",
                "### 🎮 控制模式",
                "保持张嘴并用注视选择",
                "id=dance label=舞蹈 source=expression",
                "前进一步",
                "后退一步",
            ),
        ),
        (
            "README.md",
            (
                "| **Open mouth** | `jawOpen > 0.4`",
                "| **Pucker lips** | `mouthPucker > 0.97`",
                "| **Raise inner brows** | `browInnerUp > 0.8`",
                "| **Close only the left eye** | `eyeBlinkLeft > 0.6`",
            ),
            (
                "| **Up** | `move_forward_step` | **前进** |",
                "| **Down** | `move_backward_step` | **后退** |",
                "| **Turn left** | `turn_left` | **左转** |",
                "| **Turn right** | `turn_right` | **右转** |",
                "| **Up** | `wave` | **挥手** |",
                "| **Down** | `dance` | **舞蹈** |",
                "| **Turn left** | `strafe_left` | **向左横移** |",
                "| **Turn right** | `strafe_right` | **向右横移** |",
            ),
            (
                "Left mouse click",
                "W/S keys",
                "### 🎮 Control Modes",
                "select with gaze",
                "id=dance label=舞蹈 source=expression",
                "前进一步",
                "后退一步",
            ),
        ),
    ],
)
def test_readmes_document_current_robot_action_contract(
    filename,
    expression_rows,
    wheel_rows,
    obsolete_rows,
):
    repository_root = Path(__file__).parents[1]
    text = (repository_root / filename).read_text(encoding="utf-8")

    for row in (*expression_rows, *wheel_rows):
        assert row in text
    expected_outputs = (
        ("wave", "挥手", "expression"),
        ("stop", "停止", "expression"),
        ("move_forward_step", "前进", "wheel"),
        ("move_backward_step", "后退", "wheel"),
        ("turn_left", "左转", "wheel"),
        ("turn_right", "右转", "wheel"),
        ("wave", "挥手", "wheel"),
        ("dance", "舞蹈", "wheel"),
        ("strafe_left", "向左横移", "wheel"),
        ("strafe_right", "向右横移", "wheel"),
    )
    for action_id, label, source in expected_outputs:
        assert (
            f"[ROBOT_ACTION] id={action_id} "
            f"label={label} source={source}"
        ) in text
    assert (
        "[ROBOT_ACTION_CANCELLED] reason=no_selection source=wheel"
        in text
    )
    assert "fullscreen_cardinal" in text
    assert "selection: head_pose" in text
    assert "yaw_threshold_degrees: 12.0" in text
    assert "pitch_threshold_degrees: 18.0" in text
    assert "radius: 400" not in text
    assert "regression_model_path" in text
    for obsolete in obsolete_rows:
        assert obsolete not in text
