from collections.abc import Mapping
from numbers import Integral
import uuid

from .robot_actions import RobotAction


PROTOCOL_VERSION = 1


def validate_robot_action_output_config(
    config: Mapping[str, object],
) -> dict[str, object]:
    if not isinstance(config, Mapping):
        raise TypeError("robot_action_output_config must be a mapping")
    if "type" not in config:
        raise ValueError("robot_action_output_config.type is required")

    output_type = config["type"]
    if output_type == "terminal":
        if set(config) != {"type"}:
            raise ValueError(
                "terminal output accepts only robot_action_output_config.type"
            )
        return {"type": "terminal"}

    if output_type != "sonic_ipc":
        raise ValueError(
            "robot_action_output_config.type must be 'terminal' or "
            "'sonic_ipc'"
        )

    expected_fields = {"type", "endpoint", "timeout_ms"}
    if set(config) != expected_fields:
        raise ValueError(
            "sonic_ipc output requires exactly type, endpoint, timeout_ms"
        )
    endpoint = config["endpoint"]
    if not isinstance(endpoint, str) or not endpoint.startswith("ipc://"):
        raise ValueError(
            "robot_action_output_config.endpoint must start with ipc://"
        )
    timeout_ms = config["timeout_ms"]
    if (
        isinstance(timeout_ms, bool)
        or not isinstance(timeout_ms, Integral)
        or timeout_ms <= 0
    ):
        raise ValueError(
            "robot_action_output_config.timeout_ms must be a positive integer"
        )
    return {
        "type": "sonic_ipc",
        "endpoint": endpoint,
        "timeout_ms": int(timeout_ms),
    }


class SonicActionClient:
    def __init__(self, endpoint: str, timeout_ms: int) -> None:
        validated = validate_robot_action_output_config(
            {
                "type": "sonic_ipc",
                "endpoint": endpoint,
                "timeout_ms": timeout_ms,
            }
        )
        self.endpoint = validated["endpoint"]
        self.timeout_ms = validated["timeout_ms"]

    def send(self, action: RobotAction) -> str:
        if not isinstance(action, RobotAction):
            raise TypeError("SonicActionClient.send requires RobotAction")

        try:
            import zmq
        except ModuleNotFoundError as error:
            error.add_note(
                "sonic_ipc output requires pyzmq in the active Python "
                "environment"
            )
            raise

        request_id = uuid.uuid4().hex
        if action.action_id == "stop":
            request = {
                "version": PROTOCOL_VERSION,
                "request_id": request_id,
                "command": "reset_reference_motion",
            }
        else:
            request = {
                "version": PROTOCOL_VERSION,
                "request_id": request_id,
                "command": "play_action",
                "action_id": action.action_id,
            }

        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.setsockopt(zmq.LINGER, 0)
        socket.setsockopt(zmq.SNDTIMEO, self.timeout_ms)
        socket.setsockopt(zmq.RCVTIMEO, self.timeout_ms)
        try:
            socket.connect(self.endpoint)
            socket.send_json(request)
            response = socket.recv_json()
        except zmq.Again as error:
            raise TimeoutError(
                f"SONIC did not acknowledge request {request_id} within "
                f"{self.timeout_ms} ms at {self.endpoint}"
            ) from error
        finally:
            socket.close()
            context.term()

        self._validate_response(response, request_id)
        return request_id

    @staticmethod
    def _validate_response(response: object, request_id: str) -> None:
        if not isinstance(response, dict):
            raise RuntimeError(
                "SONIC response must be a JSON object, got "
                f"{type(response).__name__}"
            )
        required_fields = {"version", "request_id", "status"}
        missing_fields = required_fields.difference(response)
        if missing_fields:
            raise RuntimeError(
                "SONIC response is missing fields: "
                + ", ".join(sorted(missing_fields))
            )
        if response["version"] != PROTOCOL_VERSION:
            raise RuntimeError(
                f"SONIC response version must equal {PROTOCOL_VERSION}, "
                f"got {response['version']!r}"
            )
        if response["request_id"] != request_id:
            raise RuntimeError(
                "SONIC response request_id mismatch: "
                f"expected {request_id!r}, got {response['request_id']!r}"
            )
        if response["status"] == "accepted":
            if set(response) != required_fields:
                raise RuntimeError(
                    "accepted SONIC response contains unexpected fields: "
                    + ", ".join(sorted(set(response) - required_fields))
                )
            return
        if response["status"] == "rejected":
            if set(response) != required_fields | {"error"}:
                raise RuntimeError(
                    "rejected SONIC response must contain exactly "
                    "version, request_id, status, error"
                )
            error_message = response["error"]
            if not isinstance(error_message, str) or not error_message:
                raise RuntimeError(
                    "rejected SONIC response error must be a non-empty string"
                )
            raise RuntimeError(
                f"SONIC rejected request {request_id}: {error_message}"
            )
        raise RuntimeError(
            f"SONIC response has unknown status: {response['status']!r}"
        )
