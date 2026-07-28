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
        "move_forward_step": "前进一步",
        "move_backward_step": "后退一步",
        "turn_left": "左转",
        "turn_right": "右转",
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
        "num8": {"action": "dance"},
        "extra": {"action": "stop"},
    },
}


@pytest.fixture
def valid_config():
    return copy.deepcopy(VALID_CONFIG)


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
                "| **抬头** | `move_forward_step` | **前进一步** |",
                "| **低头** | `move_backward_step` | **后退一步** |",
                "| **向左转头** | `turn_left` | **左转** |",
                "| **向右转头** | `turn_right` | **右转** |",
            ),
            (
                "鼠标左键点击",
                "W/S键",
                "### 🎮 控制模式",
                "保持张嘴并用注视选择",
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
                "| **Up** | `move_forward_step` | **前进一步** |",
                "| **Down** | `move_backward_step` | **后退一步** |",
                "| **Turn left** | `turn_left` | **左转** |",
                "| **Turn right** | `turn_right` | **右转** |",
            ),
            (
                "Left mouse click",
                "W/S keys",
                "### 🎮 Control Modes",
                "select with gaze",
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
    for action_id, label in VALID_CONFIG["actions"].items():
        source = (
            "wheel"
            if action_id
            in VALID_CONFIG["expressions"]["numlock"]["wheel"]
            else "expression"
        )
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
    assert "pitch_threshold_degrees: 10.0" in text
    assert "radius: 400" not in text
    assert "regression_model_path" in text
    for obsolete in obsolete_rows:
        assert obsolete not in text
