"""Win32 desktop input and pointer operations."""

import ctypes
import threading
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32print


_LETTER_SCANS = {
    "a": 0x1E, "b": 0x30, "c": 0x2E, "d": 0x20, "e": 0x12,
    "f": 0x21, "g": 0x22, "h": 0x23, "i": 0x17, "j": 0x24,
    "k": 0x25, "l": 0x26, "m": 0x32, "n": 0x31, "o": 0x18,
    "p": 0x19, "q": 0x10, "r": 0x13, "s": 0x1F, "t": 0x14,
    "u": 0x16, "v": 0x2F, "w": 0x11, "x": 0x2D, "y": 0x15,
    "z": 0x2C,
}
_DIGIT_SCANS = {
    "0": 0x0B, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05,
    "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A,
}

KEY_MAP = {
    key: {"vk": ord(key.upper()), "scan": scan}
    for key, scan in _LETTER_SCANS.items()
}
KEY_MAP.update(
    {
        key: {"vk": ord(key), "scan": scan}
        for key, scan in _DIGIT_SCANS.items()
    }
)

for _name, _vk_name, _scan in (
    ("f1", "VK_F1", 0x3B),
    ("f2", "VK_F2", 0x3C),
    ("f3", "VK_F3", 0x3D),
    ("f4", "VK_F4", 0x3E),
    ("f5", "VK_F5", 0x3F),
    ("f6", "VK_F6", 0x40),
    ("f7", "VK_F7", 0x41),
    ("f8", "VK_F8", 0x42),
    ("f9", "VK_F9", 0x43),
    ("f10", "VK_F10", 0x44),
    ("f11", "VK_F11", 0x57),
    ("f12", "VK_F12", 0x58),
    ("shift", "VK_LSHIFT", 0x2A),
    ("ctrl", "VK_LCONTROL", 0x1D),
    ("alt", "VK_LMENU", 0x38),
    ("space", "VK_SPACE", 0x39),
    ("enter", "VK_RETURN", 0x1C),
    ("backspace", "VK_BACK", 0x0E),
    ("tab", "VK_TAB", 0x0F),
    ("esc", "VK_ESCAPE", 0x01),
    ("caps_lock", "VK_CAPITAL", 0x3A),
    ("numpad0", "VK_NUMPAD0", 0x52),
    ("numpad1", "VK_NUMPAD1", 0x4F),
    ("numpad2", "VK_NUMPAD2", 0x50),
    ("numpad3", "VK_NUMPAD3", 0x51),
    ("numpad4", "VK_NUMPAD4", 0x4B),
    ("numpad5", "VK_NUMPAD5", 0x4C),
    ("numpad6", "VK_NUMPAD6", 0x4D),
    ("numpad7", "VK_NUMPAD7", 0x47),
    ("numpad8", "VK_NUMPAD8", 0x48),
    ("numpad9", "VK_NUMPAD9", 0x49),
    ("numpad_multiply", "VK_MULTIPLY", 0x37),
    ("numpad_add", "VK_ADD", 0x4E),
    ("numpad_subtract", "VK_SUBTRACT", 0x4A),
    ("numpad_decimal", "VK_DECIMAL", 0x53),
    ("numpad_divide", "VK_DIVIDE", 0xB5),
    ("num_lock", "VK_NUMLOCK", 0x45),
    ("left", "VK_LEFT", 0xCB),
    ("right", "VK_RIGHT", 0xCD),
    ("up", "VK_UP", 0xC8),
    ("down", "VK_DOWN", 0xD0),
    ("insert", "VK_INSERT", 0xD2),
    ("delete", "VK_DELETE", 0xD3),
    ("home", "VK_HOME", 0xC7),
    ("end", "VK_END", 0xCF),
    ("page_up", "VK_PRIOR", 0xC9),
    ("page_down", "VK_NEXT", 0xD1),
    ("print_screen", "VK_PRINT", 0x37),
    ("scroll_lock", "VK_SCROLL", 0x46),
    ("pause", "VK_PAUSE", 0xC5),
    ("right_shift", "VK_RSHIFT", 0x36),
    ("right_ctrl", "VK_RCONTROL", 0x1D),
    ("right_alt", "VK_RMENU", 0x38),
    ("win", "VK_LWIN", 0xDB),
    ("right_win", "VK_RWIN", 0xDC),
    ("apps", "VK_APPS", 0xDD),
):
    KEY_MAP[_name] = {"vk": getattr(win32con, _vk_name), "scan": _scan}

KEY_MAP.update(
    {
        "-": {"vk": 0xBD, "scan": 0x0C},
        "=": {"vk": 0xBB, "scan": 0x0D},
        ",": {"vk": 0xBC, "scan": 0x33},
        ".": {"vk": 0xBE, "scan": 0x34},
        ";": {"vk": 0xBA, "scan": 0x27},
        "/": {"vk": 0xBF, "scan": 0x35},
        "`": {"vk": 0xC0, "scan": 0x29},
        "[": {"vk": 0xDB, "scan": 0x1A},
        "\\": {"vk": 0xDC, "scan": 0x2B},
        "]": {"vk": 0xDD, "scan": 0x1B},
        "'": {"vk": 0xDE, "scan": 0x28},
        "mouse_left": {
            "vk": win32con.VK_LBUTTON,
            "scan": 0,
            "is_mouse": True,
            "down_flag": win32con.MOUSEEVENTF_LEFTDOWN,
            "up_flag": win32con.MOUSEEVENTF_LEFTUP,
        },
        "mouse_right": {
            "vk": win32con.VK_RBUTTON,
            "scan": 0,
            "is_mouse": True,
            "down_flag": win32con.MOUSEEVENTF_RIGHTDOWN,
            "up_flag": win32con.MOUSEEVENTF_RIGHTUP,
        },
        "mouse_middle": {
            "vk": win32con.VK_MBUTTON,
            "scan": 0,
            "is_mouse": True,
            "down_flag": win32con.MOUSEEVENTF_MIDDLEDOWN,
            "up_flag": win32con.MOUSEEVENTF_MIDDLEUP,
        },
        "mouse_x1": {
            "vk": 0x05,
            "scan": 0,
            "is_mouse": True,
            "down_flag": win32con.MOUSEEVENTF_XDOWN,
            "up_flag": win32con.MOUSEEVENTF_XUP,
            "x_flag": 0x0001,
        },
        "mouse_x2": {
            "vk": 0x06,
            "scan": 0,
            "is_mouse": True,
            "down_flag": win32con.MOUSEEVENTF_XDOWN,
            "up_flag": win32con.MOUSEEVENTF_XUP,
            "x_flag": 0x0002,
        },
    }
)


class CURSORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hCursor", wintypes.HANDLE),
        ("ptScreenPos", wintypes.POINT),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_get_cursor_info = _user32.GetCursorInfo
_get_cursor_info.argtypes = [ctypes.POINTER(CURSORINFO)]
_get_cursor_info.restype = wintypes.BOOL

_held_inputs = set()
_held_lock = threading.RLock()


def initialize():
    return None


def close():
    release_all()


def get_screen_size():
    desktop_dc = win32gui.GetDC(0)
    if not desktop_dc:
        raise RuntimeError("GetDC(0) failed")
    try:
        width = win32print.GetDeviceCaps(
            desktop_dc, win32con.DESKTOPHORZRES
        )
        height = win32print.GetDeviceCaps(
            desktop_dc, win32con.DESKTOPVERTRES
        )
    except BaseException as error:
        try:
            win32gui.ReleaseDC(0, desktop_dc)
        except BaseException as release_error:
            error.add_note(
                "ReleaseDC after GetDeviceCaps failure also failed: "
                f"{release_error!r}"
            )
        raise
    released = win32gui.ReleaseDC(0, desktop_dc)
    if not released:
        raise RuntimeError("ReleaseDC(0, desktop_dc) failed")
    return width, height


def get_pointer_position():
    return win32api.GetCursorPos()


def move_pointer(x, y, relative=False):
    if relative:
        win32api.mouse_event(
            win32con.MOUSEEVENTF_MOVE, int(x), int(y), 0, 0
        )
    else:
        win32api.SetCursorPos((int(x), int(y)))


def _key_info(key):
    name = key.lower()
    if name not in KEY_MAP:
        raise ValueError(f"未知的按键: {key}")
    return name, KEY_MAP[name]


def key_down(key):
    name, key_info = _key_info(key)
    with _held_lock:
        if key_info.get("is_mouse", False):
            win32api.mouse_event(
                key_info["down_flag"], 0, 0, key_info.get("x_flag", 0), 0
            )
        else:
            win32api.keybd_event(key_info["vk"], key_info["scan"], 0, 0)
        _held_inputs.add(name)


def key_up(key):
    name, key_info = _key_info(key)
    with _held_lock:
        if key_info.get("is_mouse", False):
            win32api.mouse_event(
                key_info["up_flag"], 0, 0, key_info.get("x_flag", 0), 0
            )
        else:
            win32api.keybd_event(
                key_info["vk"], key_info["scan"], win32con.KEYEVENTF_KEYUP, 0
            )
        _held_inputs.discard(name)


def is_key_down(key):
    _, key_info = _key_info(key)
    return bool(win32api.GetAsyncKeyState(key_info["vk"]) & 0x8000)


def are_keys_down(keys):
    return all(is_key_down(key) for key in keys)


def supports_key(key):
    return isinstance(key, str) and key.lower() in KEY_MAP


def scroll(steps):
    win32api.mouse_event(
        win32con.MOUSEEVENTF_WHEEL,
        0,
        0,
        int(steps) * win32con.WHEEL_DELTA,
        0,
    )


def is_cursor_visible():
    cursor_info = CURSORINFO()
    cursor_info.cbSize = ctypes.sizeof(CURSORINFO)
    if not _get_cursor_info(ctypes.byref(cursor_info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return cursor_info.flags != 0


def release_all():
    errors = []
    with _held_lock:
        held_inputs = tuple(sorted(_held_inputs))
        for key in held_inputs:
            try:
                key_up(key)
            except Exception as error:
                errors.append(error)
    if errors:
        raise ExceptionGroup("failed to release Win32 inputs", errors)
