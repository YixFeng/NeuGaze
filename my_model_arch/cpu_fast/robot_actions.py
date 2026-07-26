from collections.abc import Mapping
import copy
from dataclasses import dataclass
import sys
from typing import Literal, TextIO


_REQUIRED_ACTION_IDS = (
    "move_forward_step",
    "move_backward_step",
    "turn_left",
    "turn_right",
    "wave",
    "dance",
    "stop",
)


@dataclass(frozen=True, slots=True)
class RobotAction:
    action_id: str
    label: str
    source: Literal["wheel", "expression"]

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id:
            raise ValueError("RobotAction.action_id must be a non-empty string")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("RobotAction.label must be a non-empty string")
        if self.source not in ("wheel", "expression"):
            raise ValueError(
                "RobotAction.source must be 'wheel' or 'expression'"
            )


def emit_robot_action(
    action: RobotAction, stream: TextIO | None = None
) -> None:
    if not isinstance(action, RobotAction):
        raise TypeError("emit_robot_action requires RobotAction")
    output = sys.stdout if stream is None else stream
    print(
        f"[ROBOT_ACTION] id={action.action_id} "
        f"label={action.label} source={action.source}",
        file=output,
        flush=True,
    )


def emit_robot_action_cancelled(
    *, reason: str, source: str, stream: TextIO | None = None
) -> None:
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason must be a non-empty string")
    if not isinstance(source, str) or not source:
        raise ValueError("source must be a non-empty string")
    output = sys.stdout if stream is None else stream
    print(
        f"[ROBOT_ACTION_CANCELLED] reason={reason} source={source}",
        file=output,
        flush=True,
    )


def validate_robot_action_config(
    config: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(config, Mapping):
        raise TypeError("robot_action_config must be a mapping")

    expected_top_level_keys = {"actions", "expressions"}
    for key in config:
        if key not in expected_top_level_keys:
            raise ValueError(f"robot_action_config.{key} is not allowed")
    for key in expected_top_level_keys:
        if key not in config:
            raise ValueError(f"robot_action_config.{key} is required")

    actions = config["actions"]
    if not isinstance(actions, Mapping):
        raise TypeError("robot_action_config.actions must be a mapping")
    for action_id in actions:
        if action_id not in _REQUIRED_ACTION_IDS:
            raise ValueError(f"actions.{action_id} is not allowed")
    for action_id in _REQUIRED_ACTION_IDS:
        if action_id not in actions:
            raise ValueError(f"actions.{action_id} is required")
    for action_id, label in actions.items():
        field_path = f"actions.{action_id}"
        if not isinstance(action_id, str) or not action_id:
            raise ValueError(f"{field_path} has an invalid action id")
        if not isinstance(label, str) or not label:
            raise ValueError(f"{field_path} must be a non-empty string")

    expressions = config["expressions"]
    if not isinstance(expressions, Mapping):
        raise TypeError("robot_action_config.expressions must be a mapping")
    for expression_id, expression_config in expressions.items():
        field_path = f"expressions.{expression_id}"
        if not isinstance(expression_id, str) or not expression_id:
            raise ValueError(f"{field_path} has an invalid expression id")
        if not isinstance(expression_config, Mapping):
            raise TypeError(f"{field_path} must be a mapping")

        keys = set(expression_config)
        if keys not in ({"action"}, {"wheel"}):
            raise ValueError(
                f"{field_path} must contain exactly one of 'action' or 'wheel'"
            )

        if "action" in expression_config:
            action_id = expression_config["action"]
            if not isinstance(action_id, str) or not action_id:
                raise ValueError(
                    f"{field_path}.action must be a non-empty action id"
                )
            if action_id not in actions:
                raise ValueError(
                    f"{field_path}.action references unknown action id "
                    f"{action_id!r}"
                )
            continue

        wheel = expression_config["wheel"]
        if not isinstance(wheel, list) or len(wheel) != 4:
            raise ValueError(
                f"{field_path}.wheel must contain exactly four action ids"
            )
        seen_action_ids = set()
        for action_id in wheel:
            if not isinstance(action_id, str) or not action_id:
                raise ValueError(
                    f"{field_path}.wheel contains an invalid action id"
                )
            if action_id in seen_action_ids:
                raise ValueError(
                    f"{field_path}.wheel contains duplicate action id "
                    f"{action_id!r}"
                )
            if action_id not in actions:
                raise ValueError(
                    f"{field_path}.wheel references unknown action id "
                    f"{action_id!r}"
                )
            seen_action_ids.add(action_id)

    return copy.deepcopy(config)


def resolve_robot_action(
    config: Mapping[str, object], action_id: str, source: str
) -> RobotAction:
    validated_config = validate_robot_action_config(config)
    actions = validated_config["actions"]
    if not isinstance(action_id, str) or action_id not in actions:
        raise ValueError(f"unknown robot action id: {action_id!r}")
    return RobotAction(action_id, actions[action_id], source)
