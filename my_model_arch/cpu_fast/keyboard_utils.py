"""Platform-neutral keyboard actions."""

import time
from dataclasses import dataclass
from enum import Enum, auto

from . import desktop


class OpType(Enum):
    """Keyboard operation type."""

    KEYDOWN = auto()
    KEYDOWN_SAFE = auto()
    KEYUP = auto()
    KEYPRESS = auto()
    KEYUP_SAFE = auto()
    NONE = auto()


@dataclass
class Action:
    """A keyboard action executed synchronously by the selected desktop backend."""

    keyname: str
    op_type: OpType
    duration: float = 0.01

    def execute(self):
        if self.op_type == OpType.KEYDOWN:
            keydown(self.keyname)
        elif self.op_type == OpType.KEYDOWN_SAFE:
            return keydown_safe(self.keyname)
        elif self.op_type == OpType.KEYUP:
            keyup(self.keyname)
        elif self.op_type == OpType.KEYPRESS:
            keypress(self.keyname, self.duration)
        elif self.op_type == OpType.KEYUP_SAFE:
            return keyup_safe(self.keyname)
        elif self.op_type == OpType.NONE:
            return None
        else:
            raise ValueError(f"unsupported op_type: {self.op_type!r}")


def keydown(key):
    desktop.key_down(key)


def keyup(key):
    desktop.key_up(key)


def keypress(key, duration=0.01):
    desktop.key_down(key)
    time.sleep(duration)
    desktop.key_up(key)


def is_key_down(key):
    return desktop.is_key_down(key)


def keydown_safe(key):
    if desktop.is_key_down(key):
        return False
    desktop.key_down(key)
    return True


def keyup_safe(key):
    return desktop.key_up_owned(key)
