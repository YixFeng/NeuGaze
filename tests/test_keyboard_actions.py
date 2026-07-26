import pytest

from my_model_arch.cpu_fast import desktop
from my_model_arch.cpu_fast import keyboard_utils
from my_model_arch.cpu_fast.keyboard_utils import Action, OpType


def test_action_executes_keydown_synchronously(monkeypatch):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop, "key_down", lambda key: calls.append(("down", key))
    )

    assert Action("w", OpType.KEYDOWN).execute() is None
    assert calls == [("down", "w")]


def test_action_executes_safe_keydown_and_returns_result(monkeypatch):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop, "is_key_down", lambda key: calls.append(("is", key)) or False
    )
    monkeypatch.setattr(
        keyboard_utils.desktop, "key_down", lambda key: calls.append(("down", key))
    )

    assert Action("w", OpType.KEYDOWN_SAFE).execute() is True
    assert calls == [("is", "w"), ("down", "w")]


def test_action_executes_keyup_synchronously(monkeypatch):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop, "key_up", lambda key: calls.append(("up", key))
    )

    assert Action("w", OpType.KEYUP).execute() is None
    assert calls == [("up", "w")]


def test_action_executes_keypress_with_duration(monkeypatch):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop, "key_down", lambda key: calls.append(("down", key))
    )
    monkeypatch.setattr(
        keyboard_utils.time, "sleep", lambda duration: calls.append(("sleep", duration))
    )
    monkeypatch.setattr(
        keyboard_utils.desktop, "key_up", lambda key: calls.append(("up", key))
    )

    assert Action("w", OpType.KEYPRESS, duration=0.25).execute() is None
    assert calls == [("down", "w"), ("sleep", 0.25), ("up", "w")]


@pytest.mark.parametrize("owned", [False, True])
def test_action_safe_keyup_returns_owned_release_result(monkeypatch, owned):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_up_owned",
        lambda key: calls.append(key) or owned,
        raising=False,
    )
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "is_key_down",
        lambda key: pytest.fail("safe keyup must not query global state"),
    )
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_up",
        lambda key: pytest.fail("safe keyup must not release globally"),
    )

    assert Action("w", OpType.KEYUP_SAFE).execute() is owned
    assert calls == ["w"]


def test_action_none_does_nothing(monkeypatch):
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_down",
        lambda key: pytest.fail("OpType.NONE must not inject input"),
    )
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_up",
        lambda key: pytest.fail("OpType.NONE must not inject input"),
    )

    assert Action("w", OpType.NONE).execute() is None


def test_unknown_key_error_is_not_rewritten(monkeypatch):
    error = ValueError("unsupported key 'unknown'")

    def reject(key):
        raise error

    monkeypatch.setattr(keyboard_utils.desktop, "key_down", reject)

    with pytest.raises(ValueError, match="unsupported key 'unknown'") as caught:
        keyboard_utils.keydown("unknown")
    assert caught.value is error


def test_safe_keydown_returns_false_when_key_is_already_held(monkeypatch):
    monkeypatch.setattr(keyboard_utils.desktop, "is_key_down", lambda key: True)
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_down",
        lambda key: pytest.fail("already-held key must not be pressed again"),
    )

    assert keyboard_utils.keydown_safe("w") is False


@pytest.mark.parametrize("owned", [False, True])
def test_safe_keyup_delegates_once_to_owned_release(monkeypatch, owned):
    calls = []
    monkeypatch.setattr(
        keyboard_utils.desktop,
        "key_up_owned",
        lambda key: calls.append(key) or owned,
        raising=False,
    )

    assert keyboard_utils.keyup_safe("w") is owned
    assert calls == ["w"]


def test_action_rejects_removed_safe_keyup_compatibility_arguments():
    with pytest.raises(TypeError):
        Action("w", OpType.KEYUP_SAFE, ensure_release=True)


def test_action_propagates_backend_error(monkeypatch):
    def fail(key):
        raise OSError("injection failed")

    monkeypatch.setattr(keyboard_utils.desktop, "key_down", fail)

    with pytest.raises(OSError, match="injection failed"):
        Action("w", OpType.KEYDOWN).execute()



def test_action_rejects_illegal_op_type():
    with pytest.raises(ValueError, match="op_type"):
        Action("w", object()).execute()
