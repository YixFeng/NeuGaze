import sys
import threading
from types import SimpleNamespace

import pytest

from my_model_arch.cpu_fast.robot_actions import RobotAction
from my_model_arch.cpu_fast.sonic_action_client import (
    SonicActionClient,
    validate_robot_action_output_config,
)


class FakeSocket:
    def __init__(self, response):
        self.response = response
        self.endpoint = None
        self.request = None
        self.closed = False

    def setsockopt(self, option, value):
        pass

    def connect(self, endpoint):
        self.endpoint = endpoint

    def send_json(self, request):
        self.request = request

    def recv_json(self):
        response = dict(self.response)
        response["request_id"] = self.request["request_id"]
        return response

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, socket):
        self._socket = socket
        self.terminated = False

    def socket(self, socket_type):
        return self._socket

    def term(self):
        self.terminated = True


def install_fake_zmq(monkeypatch, response):
    socket = FakeSocket(response)
    context = FakeContext(socket)
    module = SimpleNamespace(
        REQ=1,
        LINGER=2,
        SNDTIMEO=3,
        RCVTIMEO=4,
        Again=TimeoutError,
        Context=lambda: context,
    )
    monkeypatch.setitem(sys.modules, "zmq", module)
    return socket, context


@pytest.mark.parametrize(
    "config, message",
    [
        ({}, "type is required"),
        ({"type": "missing"}, "terminal.*sonic_ipc"),
        (
            {"type": "terminal", "endpoint": "ipc:///tmp/test.sock"},
            "terminal output accepts only",
        ),
        (
            {
                "type": "sonic_ipc",
                "endpoint": "tcp://localhost:5555",
                "timeout_ms": 1000,
            },
            "must start with ipc://",
        ),
        (
            {
                "type": "sonic_ipc",
                "endpoint": "ipc:///tmp/test.sock",
                "timeout_ms": 0,
            },
            "positive integer",
        ),
    ],
)
def test_output_config_is_strict(config, message):
    with pytest.raises((TypeError, ValueError), match=message):
        validate_robot_action_output_config(config)


def test_play_action_sends_only_stable_action_id(monkeypatch):
    socket, context = install_fake_zmq(
        monkeypatch,
        {"version": 1, "status": "accepted"},
    )
    client = SonicActionClient("ipc:///tmp/neugaze-sonic.sock", 750)

    request_id = client.send(RobotAction("turn_left", "左转", "wheel"))

    assert socket.request == {
        "version": 1,
        "request_id": request_id,
        "command": "play_action",
        "action_id": "turn_left",
    }
    assert socket.endpoint == "ipc:///tmp/neugaze-sonic.sock"
    assert socket.closed is True
    assert context.terminated is True


def test_stop_maps_to_reference_motion_reset(monkeypatch):
    socket, _ = install_fake_zmq(
        monkeypatch,
        {"version": 1, "status": "accepted"},
    )
    client = SonicActionClient("ipc:///tmp/neugaze-sonic.sock", 1000)

    request_id = client.send(RobotAction("stop", "停止", "expression"))

    assert socket.request == {
        "version": 1,
        "request_id": request_id,
        "command": "reset_reference_motion",
    }


def test_rejection_preserves_server_error(monkeypatch):
    install_fake_zmq(
        monkeypatch,
        {
            "version": 1,
            "status": "rejected",
            "error": "unknown action_id: missing",
        },
    )
    client = SonicActionClient("ipc:///tmp/neugaze-sonic.sock", 1000)

    with pytest.raises(RuntimeError, match="unknown action_id: missing"):
        client.send(RobotAction("turn_left", "左转", "wheel"))


def test_real_pyzmq_ipc_roundtrip(tmp_path):
    zmq = pytest.importorskip("zmq")
    endpoint = f"ipc://{tmp_path}/sonic.sock"
    received = []

    def serve_once():
        context = zmq.Context()
        socket = context.socket(zmq.REP)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(endpoint)
            request = socket.recv_json()
            received.append(request)
            socket.send_json(
                {
                    "version": 1,
                    "request_id": request["request_id"],
                    "status": "accepted",
                }
            )
        finally:
            socket.close()
            context.term()

    server = threading.Thread(target=serve_once)
    server.start()
    client = SonicActionClient(endpoint, 1000)
    request_id = client.send(RobotAction("wave", "挥手", "wheel"))
    server.join(timeout=2)

    assert not server.is_alive()
    assert received == [
        {
            "version": 1,
            "request_id": request_id,
            "command": "play_action",
            "action_id": "wave",
        }
    ]
