"""Run one calibration in a PySide-free Linux worker process."""

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import re
import sys
from typing import BinaryIO

import yaml

from . import desktop


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RESULT_PREFIX = b"NEUGAZE_CALIBRATION_RESULT="
CALIBRATION_TIME = re.compile(r"\A\d{8}_\d{6}\Z")
HIGHGUI_INITIALIZATION_WINDOW = "__neugaze_highgui_init__"
RealAction = None


def parse_calibration_result(
    stdout: bytes, repository_root: Path
) -> tuple[str, str]:
    result_lines = [
        line for line in stdout.splitlines() if line.startswith(RESULT_PREFIX)
    ]
    if len(result_lines) != 1:
        raise RuntimeError(
            "calibration worker stdout must contain exactly one "
            f"{RESULT_PREFIX.decode('ascii')} line; got {len(result_lines)}"
        )

    payload = json.loads(
        result_lines[0][len(RESULT_PREFIX) :].decode("utf-8")
    )
    if not isinstance(payload, dict) or set(payload) != {
        "calibration_time",
        "model_path",
    }:
        raise ValueError(
            "calibration result must contain exactly calibration_time and "
            "model_path"
        )

    calibration_time = payload["calibration_time"]
    model_path = payload["model_path"]
    if not isinstance(calibration_time, str) or not isinstance(model_path, str):
        raise TypeError(
            "calibration result calibration_time and model_path values must "
            "be strings"
        )
    if CALIBRATION_TIME.fullmatch(calibration_time) is None:
        raise ValueError(f"invalid calibration_time {calibration_time!r}")

    expected = f"model_weights/{calibration_time}/model.pkl"
    if model_path != expected:
        raise ValueError(f"model_path must equal {expected!r}")

    root = repository_root.resolve()
    resolved = (root / Path(model_path)).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("model_path escapes repository root")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return calibration_time, expected


def load_config(config_path: Path) -> Mapping[str, object]:
    with config_path.open(encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)
    if not isinstance(config, Mapping):
        raise TypeError("calibration configuration must be a mapping")
    return config


def initialize_highgui() -> None:
    import cv2

    cv2.namedWindow(HIGHGUI_INITIALIZATION_WINDOW, cv2.WINDOW_NORMAL)
    try:
        cv2.waitKey(1)
    except BaseException as error:
        try:
            cv2.destroyWindow(HIGHGUI_INITIALIZATION_WINDOW)
        except BaseException as cleanup_error:
            error.add_note(
                "HighGUI initialization window cleanup also failed: "
                f"{cleanup_error!r}"
            )
        raise
    cv2.destroyWindow(HIGHGUI_INITIALIZATION_WINDOW)


def _real_action_class():
    if RealAction is not None:
        return RealAction

    # Importing pipeline loads torchvision. On the deployed OpenCV Qt5 build,
    # HighGUI must be initialized first or cv2.namedWindow busy-loops.
    from .pipeline import RealAction as real_action_class

    return real_action_class


def build_pipeline(config: Mapping[str, object]):
    return _real_action_class()(
        **config["real_action_config"],
        gaze_config=config["gaze_config"],
        mouse_control_config=config["mouse_control_config"],
        wheel_config=config["wheel_config"],
        configuration=config["key_config"],
        robot_wheel_config=config.get("robot_wheel_config"),
        robot_action_config=config.get("robot_action_config"),
        head_angles_center=config["head_angles_center"],
        head_angles_scale=config["head_angles_scale"],
        expression_evaluator_config=config["expression_evaluator_config"],
        **config["integrated_config"],
    )


def run_calibration(
    config_path: Path,
    output: BinaryIO,
    repository_root: Path = REPOSITORY_ROOT,
) -> tuple[str, str]:
    root = repository_root.resolve()
    model_root = root / "model_weights"
    preexisting_models = {
        path.resolve()
        for path in model_root.glob("*/model.pkl")
        if path.is_file()
    }
    pipeline = None
    pipeline_cleanup_attempted = False
    desktop_cleanup_attempted = False
    desktop.initialize()
    try:
        config = load_config(config_path)
        pipeline = build_pipeline(config)
        completed = pipeline.start_calibration()
        if completed is not True:
            raise RuntimeError("calibration did not complete")

        payload = {
            "calibration_time": pipeline.calibration_time,
            "model_path": (
                f"model_weights/{pipeline.calibration_time}/model.pkl"
            ),
        }
        produced_model = (root / payload["model_path"]).resolve()
        if produced_model in preexisting_models:
            raise RuntimeError(
                f"calibration model existed before calibration: {produced_model}"
            )
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        calibration_time, model_path = parse_calibration_result(
            RESULT_PREFIX + payload_bytes, root
        )

        if not pipeline.quit:
            pipeline_cleanup_attempted = True
            pipeline.quit_pipeline()
        desktop_cleanup_attempted = True
        desktop.close()
    except BaseException as error:
        if (
            pipeline is not None
            and not pipeline.quit
            and not pipeline_cleanup_attempted
        ):
            try:
                pipeline_cleanup_attempted = True
                pipeline.quit_pipeline()
            except BaseException as cleanup_error:
                error.add_note(
                    f"pipeline cleanup also failed: {cleanup_error!r}"
                )
        if not desktop_cleanup_attempted:
            try:
                desktop_cleanup_attempted = True
                desktop.close()
            except BaseException as cleanup_error:
                error.add_note(
                    f"desktop cleanup also failed: {cleanup_error!r}"
                )
        raise

    result_line = RESULT_PREFIX + payload_bytes + b"\n"
    output.write(result_line)
    output.flush()
    return calibration_time, model_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    arguments = parser.parse_args()
    initialize_highgui()
    run_calibration(arguments.config, sys.stdout.buffer)


if __name__ == "__main__":
    main()
