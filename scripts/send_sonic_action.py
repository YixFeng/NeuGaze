import argparse
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from my_model_arch.cpu_fast.robot_actions import RobotAction
from my_model_arch.cpu_fast.sonic_action_client import SonicActionClient


ACTION_LABELS = {
    "move_forward_step": "前进",
    "move_backward_step": "后退",
    "turn_left": "左转",
    "turn_right": "右转",
    "strafe_left": "向左横移",
    "strafe_right": "向右横移",
    "wave": "挥手",
    "dance": "舞蹈",
    "stop": "停止",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="向本机 SONIC 发送一个 NeuGaze 动作"
    )
    parser.add_argument("action_id", choices=ACTION_LABELS)
    parser.add_argument(
        "--endpoint",
        default="ipc:///tmp/neugaze-sonic.sock",
    )
    parser.add_argument("--timeout-ms", type=int, default=1000)
    arguments = parser.parse_args()

    action = RobotAction(
        arguments.action_id,
        ACTION_LABELS[arguments.action_id],
        "expression" if arguments.action_id == "stop" else "wheel",
    )
    client = SonicActionClient(arguments.endpoint, arguments.timeout_ms)
    request_id = client.send(action)
    print(
        f"[SONIC_ACTION_ACCEPTED] request_id={request_id} "
        f"id={action.action_id} label={action.label}",
        flush=True,
    )


if __name__ == "__main__":
    main()
