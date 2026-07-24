"""X11 desktop input, pointer, and cursor operations."""

import os
import threading

from Xlib import X, XK
from Xlib import display as xdisplay
from Xlib.ext import xfixes, xtest


_NAMED_KEYSYMS = {
    **{f"f{number}": f"F{number}" for number in range(1, 13)},
    "shift": "Shift_L",
    "ctrl": "Control_L",
    "alt": "Alt_L",
    "right_shift": "Shift_R",
    "right_ctrl": "Control_R",
    "right_alt": "Alt_R",
    "win": "Super_L",
    "right_win": "Super_R",
    "apps": "Menu",
    "space": "space",
    "enter": "Return",
    "backspace": "BackSpace",
    "tab": "Tab",
    "esc": "Escape",
    "caps_lock": "Caps_Lock",
    "num_lock": "Num_Lock",
    "left": "Left",
    "right": "Right",
    "up": "Up",
    "down": "Down",
    "insert": "Insert",
    "delete": "Delete",
    "home": "Home",
    "end": "End",
    "page_up": "Page_Up",
    "page_down": "Page_Down",
    "print_screen": "Print",
    "scroll_lock": "Scroll_Lock",
    "pause": "Pause",
    **{f"numpad{number}": f"KP_{number}" for number in range(10)},
    "numpad_multiply": "KP_Multiply",
    "numpad_add": "KP_Add",
    "numpad_subtract": "KP_Subtract",
    "numpad_decimal": "KP_Decimal",
    "numpad_divide": "KP_Divide",
}

_BUTTONS = {
    "mouse_left": 1,
    "mouse_middle": 2,
    "mouse_right": 3,
    "mouse_x1": 8,
    "mouse_x2": 9,
}

_BUTTON_MASKS = {
    "mouse_left": X.Button1Mask,
    "mouse_middle": X.Button2Mask,
    "mouse_right": X.Button3Mask,
}

_display = None
_root = None
_lock = threading.RLock()
_held_keys = set()
_held_buttons = set()
_implicit_shift_keys = set()
_owns_implicit_shift = False


def _require_initialized():
    if _display is None or _root is None:
        raise RuntimeError("X11 desktop backend is not initialized; call initialize()")
    return _display, _root


def _display_name(display):
    return display.get_display_name()


def _normalized_name(key):
    if not isinstance(key, str) or not key:
        return key
    if len(key) == 1:
        return key
    return key.lower()


def _keysym_for_key(key):
    if not isinstance(key, str) or not key:
        return X.NoSymbol
    if len(key) == 1:
        codepoint = ord(key)
        if 0x20 <= codepoint <= 0x7E or 0xA0 <= codepoint <= 0xFF:
            return codepoint
        return 0x01000000 | codepoint
    symbol_name = _NAMED_KEYSYMS.get(key.lower())
    if symbol_name is None:
        return X.NoSymbol
    return XK.string_to_keysym(symbol_name)


def _find_key(key, display):
    symbol = _keysym_for_key(key)
    if symbol == X.NoSymbol:
        return None

    candidates = []
    for keycode, level in display.keysym_to_keycodes(symbol):
        if level == 0:
            candidates.append((int(keycode), 0))
        elif level == 1:
            candidates.append((int(keycode), X.ShiftMask))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[1] != 0, item[0]))


def _resolve_key(key, display):
    resolution = _find_key(key, display)
    if resolution is None:
        raise ValueError(
            f"X11 key {key!r} is unavailable on display "
            f"{_display_name(display)!r}"
        )
    return resolution


def _button_number(name):
    normalized = name.lower() if isinstance(name, str) else name
    try:
        return _BUTTONS[normalized]
    except (KeyError, AttributeError):
        raise ValueError(f"unknown X11 mouse button {name!r}") from None


def _keycode_is_down(keymap, keycode):
    if not isinstance(keycode, int) or not 0 <= keycode <= 255:
        raise ValueError(f"invalid X11 keycode {keycode!r}")
    return bool(keymap[keycode // 8] & (1 << (keycode % 8)))


def _cursor_image_visible(image, display_name):
    try:
        width = image.width
        height = image.height
        pixels = image.cursor_image
        pixel_count = len(pixels)
    except (AttributeError, TypeError) as error:
        raise RuntimeError(
            f"malformed XFixes cursor image from display {display_name!r}"
        ) from error

    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width <= 0
        or height <= 0
        or pixel_count != width * height
    ):
        raise RuntimeError(
            f"malformed XFixes cursor image from display {display_name!r}: "
            f"{width!r}x{height!r} with {pixel_count} pixels"
        )

    for pixel in pixels:
        if not isinstance(pixel, int) or not 0 <= pixel <= 0xFFFFFFFF:
            raise RuntimeError(
                f"malformed XFixes cursor pixel from display {display_name!r}: "
                f"{pixel!r}"
            )
        if pixel & 0xFF000000:
            return True
    return False


def initialize():
    global _display, _root
    with _lock:
        if (_display is None) != (_root is None):
            raise RuntimeError("X11 backend lifecycle invariant is broken")
        if _display is not None:
            return None

        session_type = os.environ.get("XDG_SESSION_TYPE")
        if session_type is not None and session_type.lower() == "wayland":
            raise RuntimeError(
                "XDG_SESSION_TYPE='wayland' is unsupported; "
                "NeuGaze requires Xorg"
            )

        display_name = os.environ.get("DISPLAY")
        if display_name is None or not display_name.strip():
            raise RuntimeError(
                f"DISPLAY must name an X11 server, got {display_name!r}"
            )

        candidate = xdisplay.Display(display_name)
        try:
            extensions = set(candidate.list_extensions())
            missing = [
                extension
                for extension in ("XTEST", "XFIXES")
                if extension not in extensions
            ]
            if missing:
                raise RuntimeError(
                    f"X11 display {display_name!r} is missing required "
                    f"extension(s): {', '.join(missing)}"
                )
            root = candidate.screen().root
        except Exception as error:
            try:
                candidate.close()
            except Exception as cleanup_error:
                raise ExceptionGroup(
                    "X11 initialization and connection cleanup failed",
                    [error, cleanup_error],
                ) from None
            raise

        _display = candidate
        _root = root


def close():
    global _display, _root, _owns_implicit_shift
    with _lock:
        if _display is None and _root is None:
            return None
        display, _ = _require_initialized()
        release_all()
        display.close()
        _display = None
        _root = None
        _held_keys.clear()
        _held_buttons.clear()
        _implicit_shift_keys.clear()
        _owns_implicit_shift = False


def get_screen_size():
    with _lock:
        _, root = _require_initialized()
        geometry = root.get_geometry()
        return int(geometry.width), int(geometry.height)


def get_pointer_position():
    with _lock:
        _, root = _require_initialized()
        pointer = root.query_pointer()
        return int(pointer.root_x), int(pointer.root_y)


def move_pointer(x, y, relative=False):
    with _lock:
        display, root = _require_initialized()
        target_x = int(x)
        target_y = int(y)
        if relative:
            pointer = root.query_pointer()
            target_x += int(pointer.root_x)
            target_y += int(pointer.root_y)
        xtest.fake_input(
            display,
            X.MotionNotify,
            x=target_x,
            y=target_y,
        )
        display.flush()


def _is_button_name(key):
    return isinstance(key, str) and key.lower() in _BUTTONS


def _modifier_keycode(display, modifiers):
    if modifiers & X.ShiftMask:
        shift_keycode, _ = _resolve_key("shift", display)
        return shift_keycode
    return None


def _release_button_number(display, button, held_entry):
    xtest.fake_input(display, X.ButtonRelease, button)
    display.flush()
    _held_buttons.discard(held_entry)


def key_down(key):
    global _owns_implicit_shift
    with _lock:
        display, _ = _require_initialized()
        name = _normalized_name(key)
        if _is_button_name(name):
            xtest.fake_input(display, X.ButtonPress, _button_number(name))
            _held_buttons.add(name)
            display.flush()
            return None

        keycode, modifiers = _resolve_key(name, display)
        modifier_keycode = _modifier_keycode(display, modifiers)
        acquired_modifier = False
        if modifier_keycode is not None:
            modifier_is_down = _keycode_is_down(
                display.query_keymap(), modifier_keycode
            )
            if not modifier_is_down:
                xtest.fake_input(display, X.KeyPress, modifier_keycode)
                _owns_implicit_shift = True
                _implicit_shift_keys.add(name)
                _held_keys.add(name)
                acquired_modifier = True
        xtest.fake_input(display, X.KeyPress, keycode)
        if modifier_keycode is not None and not acquired_modifier:
            _implicit_shift_keys.add(name)
        _held_keys.add(name)
        display.flush()


def key_up(key):
    global _owns_implicit_shift
    with _lock:
        display, _ = _require_initialized()
        name = _normalized_name(key)
        if _is_button_name(name):
            _release_button_number(display, _button_number(name), name)
            return None

        keycode, modifiers = _resolve_key(name, display)
        if (
            name == "shift"
            and name in _held_keys
            and _implicit_shift_keys
        ):
            display.flush()
            _held_keys.discard(name)
            _owns_implicit_shift = True
            return None
        modifier_keycode = _modifier_keycode(display, modifiers)
        release_owned_modifier = (
            modifier_keycode is not None
            and name in _implicit_shift_keys
            and _owns_implicit_shift
            and _implicit_shift_keys == {name}
            and "shift" not in _held_keys
        )
        xtest.fake_input(display, X.KeyRelease, keycode)
        if release_owned_modifier:
            xtest.fake_input(display, X.KeyRelease, modifier_keycode)
        display.flush()
        _held_keys.discard(name)
        _implicit_shift_keys.discard(name)
        if release_owned_modifier or (
            not _implicit_shift_keys and "shift" in _held_keys
        ):
            _owns_implicit_shift = False


def is_key_down(key):
    with _lock:
        display, root = _require_initialized()
        name = _normalized_name(key)
        if _is_button_name(name):
            if name not in _BUTTON_MASKS:
                raise RuntimeError(
                    f"X11 core pointer state cannot query {name!r} on "
                    f"display {_display_name(display)!r}"
                )
            return bool(root.query_pointer().mask & _BUTTON_MASKS[name])

        keycode, _ = _resolve_key(name, display)
        return _keycode_is_down(display.query_keymap(), keycode)


def are_keys_down(keys):
    with _lock:
        _require_initialized()
        return all(is_key_down(key) for key in keys)


def supports_key(key):
    with _lock:
        display, _ = _require_initialized()
        if _is_button_name(key):
            return True
        return _find_key(key, display) is not None


def scroll(steps):
    with _lock:
        display, _ = _require_initialized()
        count = int(steps)
        button = 4 if count > 0 else 5
        for _ in range(abs(count)):
            xtest.fake_input(display, X.ButtonPress, button)
            _held_buttons.add(button)
            xtest.fake_input(display, X.ButtonRelease, button)
            display.flush()
            _held_buttons.discard(button)


def is_cursor_visible():
    with _lock:
        display, root = _require_initialized()
        image = xfixes.get_cursor_image(display, root)
        return _cursor_image_visible(image, _display_name(display))


def release_all():
    with _lock:
        _require_initialized()
        errors = []
        for name in tuple(sorted(_held_keys)):
            try:
                key_up(name)
            except Exception as error:
                errors.append(error)
        held_buttons = tuple(
            sorted(
                _held_buttons,
                key=lambda entry: (isinstance(entry, str), str(entry)),
            )
        )
        for name in held_buttons:
            try:
                if isinstance(name, int):
                    display, _ = _require_initialized()
                    _release_button_number(display, name, name)
                else:
                    key_up(name)
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("failed to release X11 inputs", errors)
