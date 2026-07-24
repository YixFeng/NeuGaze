import subprocess
import sys
from types import SimpleNamespace

import pytest
from Xlib import X, XK

from my_model_arch.cpu_fast.desktop import x11


class FakeKeymapDisplay:
    def __init__(self, mapping, name=":test"):
        self._mapping = mapping
        self._name = name

    def keysym_to_keycodes(self, keysym):
        return iter(self._mapping.get(keysym, ()))

    def get_display_name(self):
        return self._name


def keysym(name):
    value = ord(name) if len(name) == 1 else XK.string_to_keysym(name)
    assert value != X.NoSymbol, name
    return value


def active_us_keymap():
    mapping = {}
    expected = {}
    code = 10

    shifted_pairs = (
        ("`", "~"),
        ("1", "!"),
        ("2", "@"),
        ("3", "#"),
        ("4", "$"),
        ("5", "%"),
        ("6", "^"),
        ("7", "&"),
        ("8", "*"),
        ("9", "("),
        ("0", ")"),
        ("-", "_"),
        ("=", "+"),
        ("[", "{"),
        ("]", "}"),
        ("\\", "|"),
        (";", ":"),
        ("'", '"'),
        (",", "<"),
        (".", ">"),
        ("/", "?"),
    )
    for unshifted, shifted in shifted_pairs:
        mapping[keysym(unshifted)] = ((code, 0),)
        mapping[keysym(shifted)] = ((code, 1),)
        expected[unshifted] = (code, 0)
        expected[shifted] = (code, X.ShiftMask)
        code += 1

    for letter in "abcdefghijklmnopqrstuvwxyz":
        mapping[keysym(letter)] = ((code, 0),)
        mapping[keysym(letter.upper())] = ((code, 1),)
        expected[letter] = (code, 0)
        expected[letter.upper()] = (code, X.ShiftMask)
        code += 1

    named = {
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
    for name, symbol_name in named.items():
        mapping[keysym(symbol_name)] = ((code, 0),)
        expected[name] = (code, 0)
        code += 1

    return FakeKeymapDisplay(mapping), expected


def test_resolves_letters_digits_functions_modifiers_navigation_and_numpad():
    display, expected = active_us_keymap()

    for name, resolution in expected.items():
        assert x11._resolve_key(name, display) == resolution


def test_resolves_shifted_printable_characters_from_level_one():
    display, expected = active_us_keymap()

    for name in "ABCDEFGHIJKLMNOPQRSTUVWXYZ~!@#$%^&*()_+{}|:\"<>?":
        assert x11._resolve_key(name, display) == expected[name]


@pytest.mark.parametrize(
    ("name", "button"),
    (
        ("mouse_left", 1),
        ("mouse_middle", 2),
        ("mouse_right", 3),
        ("mouse_x1", 8),
        ("mouse_x2", 9),
    ),
)
def test_resolves_mouse_buttons(name, button):
    assert x11._button_number(name) == button


@pytest.mark.parametrize("name", ("unknown", "f13", "", None))
def test_unknown_key_names_include_name_and_display(name):
    display = FakeKeymapDisplay({}, ":77")

    with pytest.raises(ValueError) as caught:
        x11._resolve_key(name, display)

    assert repr(name) in str(caught.value)
    assert ":77" in str(caught.value)


def test_known_but_unavailable_key_includes_name_and_display():
    display = FakeKeymapDisplay({}, ":88")

    with pytest.raises(ValueError) as caught:
        x11._resolve_key("f1", display)

    assert "'f1'" in str(caught.value)
    assert ":88" in str(caught.value)


@pytest.mark.parametrize(
    ("keycode", "pressed"),
    ((8, False), (9, True), (127, True), (128, False), (255, True)),
)
def test_key_state_uses_x11_query_keymap_bits(keycode, pressed):
    keymap = bytearray(32)
    if pressed:
        keymap[keycode // 8] |= 1 << (keycode % 8)

    assert x11._keycode_is_down(keymap, keycode) is pressed


def test_cursor_visibility_uses_top_byte_alpha():
    assert not x11._cursor_image_visible(
        SimpleNamespace(width=2, height=1, cursor_image=[0x00FFFFFF, 0]),
        ":90",
    )
    assert x11._cursor_image_visible(
        SimpleNamespace(width=2, height=1, cursor_image=[0, 0x01000000]),
        ":90",
    )


@pytest.mark.parametrize(
    "image",
    (
        SimpleNamespace(width=0, height=1, cursor_image=[]),
        SimpleNamespace(width=1, height=0, cursor_image=[]),
        SimpleNamespace(width=2, height=2, cursor_image=[0]),
        SimpleNamespace(width=1, height=1),
    ),
)
def test_malformed_cursor_image_raises(image):
    with pytest.raises(RuntimeError, match=":91"):
        x11._cursor_image_visible(image, ":91")


class FakeLifecycleDisplay:
    def __init__(self, extensions=("XTEST", "XFIXES")):
        self.extensions = extensions
        self.root = object()
        self.closed = 0

    def list_extensions(self):
        return list(self.extensions)

    def screen(self):
        return SimpleNamespace(root=self.root)

    def close(self):
        self.closed += 1


@pytest.fixture(autouse=True)
def reset_backend_state(monkeypatch):
    monkeypatch.setattr(x11, "_display", None)
    monkeypatch.setattr(x11, "_root", None)
    monkeypatch.setattr(x11, "_owns_implicit_shift", False)
    x11._held_keys.clear()
    x11._held_buttons.clear()
    x11._implicit_shift_keys.clear()
    yield
    x11._display = None
    x11._root = None
    x11._owns_implicit_shift = False
    x11._held_keys.clear()
    x11._held_buttons.clear()
    x11._implicit_shift_keys.clear()


def test_import_does_not_open_display():
    assert x11._display is None
    assert x11._root is None


def test_initialize_rejects_wayland_before_connect(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":1")
    called = False

    def connect(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(x11.xdisplay, "Display", connect)

    with pytest.raises(RuntimeError, match="wayland"):
        x11.initialize()

    assert not called


def test_initialize_requires_nonempty_display_before_connect(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", " ")
    called = False

    def connect(_name):
        nonlocal called
        called = True

    monkeypatch.setattr(x11.xdisplay, "Display", connect)

    with pytest.raises(RuntimeError, match="DISPLAY"):
        x11.initialize()

    assert not called


def test_initialize_requires_extensions_and_closes_failed_connection(
    monkeypatch,
):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":92")
    candidate = FakeLifecycleDisplay(("XTEST",))
    monkeypatch.setattr(x11.xdisplay, "Display", lambda _name: candidate)

    with pytest.raises(RuntimeError, match=r":92.*XFIXES"):
        x11.initialize()

    assert candidate.closed == 1
    assert x11._display is None
    assert x11._root is None


def test_initialize_and_close_lifecycle(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":93")
    candidate = FakeLifecycleDisplay()
    monkeypatch.setattr(x11.xdisplay, "Display", lambda _name: candidate)

    x11.initialize()

    assert x11._display is candidate
    assert x11._root is candidate.root

    x11.close()

    assert candidate.closed == 1
    assert x11._display is None
    assert x11._root is None


@pytest.mark.parametrize(
    "operation",
    (
        lambda: x11.get_screen_size(),
        lambda: x11.get_pointer_position(),
        lambda: x11.move_pointer(1, 2),
        lambda: x11.key_down("a"),
        lambda: x11.key_up("a"),
        lambda: x11.is_key_down("a"),
        lambda: x11.are_keys_down(("a",)),
        lambda: x11.supports_key("a"),
        lambda: x11.scroll(1),
        lambda: x11.is_cursor_visible(),
        lambda: x11.release_all(),
    ),
)
def test_operations_require_initialized_state(operation):
    with pytest.raises(RuntimeError, match="initialize"):
        operation()


def test_release_all_attempts_only_recorded_inputs_and_aggregates_failures(
    monkeypatch,
):
    x11._display = object()
    x11._root = object()
    x11._held_keys.update(("a", "b"))
    x11._held_buttons.update(("mouse_left", "mouse_x1"))
    attempted = []

    def release(name):
        attempted.append(name)
        if name in {"a", "mouse_x1"}:
            raise OSError(f"cannot release {name}")
        x11._held_keys.discard(name)
        x11._held_buttons.discard(name)

    monkeypatch.setattr(x11, "key_up", release)

    with pytest.raises(ExceptionGroup) as caught:
        x11.release_all()

    assert set(attempted) == {"a", "b", "mouse_left", "mouse_x1"}
    assert len(caught.value.exceptions) == 2
    assert x11._held_keys == {"a"}
    assert x11._held_buttons == {"mouse_x1"}


def fake_injection_display(monkeypatch):
    display, expected = active_us_keymap()
    keymap = bytearray(32)
    events = []
    display.query_keymap = lambda: keymap
    display.flush = lambda: None
    monkeypatch.setattr(x11, "_display", display)
    monkeypatch.setattr(x11, "_root", object())

    def fake_input(_display, event_type, detail=0, **_kwargs):
        events.append((event_type, detail))
        byte = detail // 8
        bit = 1 << (detail % 8)
        if event_type == X.KeyPress:
            keymap[byte] |= bit
        elif event_type == X.KeyRelease:
            keymap[byte] &= ~bit

    monkeypatch.setattr(x11.xtest, "fake_input", fake_input)
    return expected, keymap, events


def test_shift_stays_down_until_all_shifted_keys_are_released(monkeypatch):
    expected, keymap, events = fake_injection_display(monkeypatch)
    shift_code = expected["shift"][0]
    a_code = expected["A"][0]
    b_code = expected["B"][0]

    x11.key_down("A")
    x11.key_down("B")
    x11.key_up("A")

    assert x11._keycode_is_down(keymap, shift_code)
    assert x11._keycode_is_down(keymap, b_code)
    assert events == [
        (X.KeyPress, shift_code),
        (X.KeyPress, a_code),
        (X.KeyPress, b_code),
        (X.KeyRelease, a_code),
    ]

    x11.key_up("B")

    assert not x11._keycode_is_down(keymap, shift_code)
    assert events[-2:] == [
        (X.KeyRelease, b_code),
        (X.KeyRelease, shift_code),
    ]


def test_shifted_key_does_not_release_preexisting_shift(monkeypatch):
    expected, keymap, events = fake_injection_display(monkeypatch)
    shift_code = expected["shift"][0]
    a_code = expected["A"][0]
    keymap[shift_code // 8] |= 1 << (shift_code % 8)

    x11.key_down("A")
    x11.key_up("A")

    assert x11._keycode_is_down(keymap, shift_code)
    assert events == [
        (X.KeyPress, a_code),
        (X.KeyRelease, a_code),
    ]


def test_shifted_key_does_not_release_explicitly_held_shift(monkeypatch):
    expected, keymap, events = fake_injection_display(monkeypatch)
    shift_code = expected["shift"][0]

    x11.key_down("shift")
    x11.key_down("A")
    x11.key_up("A")

    assert x11._keycode_is_down(keymap, shift_code)
    assert "shift" in x11._held_keys

    x11.key_up("shift")
    assert not x11._keycode_is_down(keymap, shift_code)


def test_import_does_not_construct_display_in_fresh_interpreter():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from Xlib import display; "
                "display.Display=lambda *args, **kwargs: "
                "(_ for _ in ()).throw(AssertionError(\"connected\")); "
                "import my_model_arch.cpu_fast.desktop.x11 as backend; "
                "assert backend._display is None"
            ),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_initialize_preserves_validation_and_cleanup_failures(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":92")
    candidate = FakeLifecycleDisplay(("XTEST",))
    cleanup_error = OSError("close failed")
    candidate.close = lambda: (_ for _ in ()).throw(cleanup_error)
    monkeypatch.setattr(x11.xdisplay, "Display", lambda _name: candidate)

    with pytest.raises(ExceptionGroup) as caught:
        x11.initialize()

    assert isinstance(caught.value.exceptions[0], RuntimeError)
    assert caught.value.exceptions[1] is cleanup_error
    assert x11._display is None
    assert x11._root is None


def test_close_release_failure_keeps_lifecycle_retryable(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":93")
    candidate = FakeLifecycleDisplay()
    monkeypatch.setattr(x11.xdisplay, "Display", lambda _name: candidate)
    x11.initialize()
    release_error = OSError("release failed")
    monkeypatch.setattr(
        x11,
        "release_all",
        lambda: (_ for _ in ()).throw(release_error),
    )

    with pytest.raises(OSError) as caught:
        x11.close()

    assert caught.value is release_error
    assert x11._display is candidate
    assert x11._root is candidate.root
    assert candidate.closed == 0

    monkeypatch.setattr(x11, "release_all", lambda: None)
    x11.close()

    assert candidate.closed == 1
    assert x11._display is None
    assert x11._root is None


def test_close_display_failure_keeps_lifecycle_retryable(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("DISPLAY", ":94")
    candidate = FakeLifecycleDisplay()
    monkeypatch.setattr(x11.xdisplay, "Display", lambda _name: candidate)
    x11.initialize()
    successful_close = candidate.close
    close_error = OSError("display close failed")
    candidate.close = lambda: (_ for _ in ()).throw(close_error)

    with pytest.raises(OSError) as caught:
        x11.close()

    assert caught.value is close_error
    assert x11._display is candidate
    assert x11._root is candidate.root
    assert candidate.closed == 0

    candidate.close = successful_close
    x11.close()

    assert candidate.closed == 1
    assert x11._display is None
    assert x11._root is None


def test_explicit_shift_release_transfers_to_implicit_user(monkeypatch):
    expected, keymap, events = fake_injection_display(monkeypatch)
    shift_code = expected["shift"][0]
    a_code = expected["A"][0]

    x11.key_down("shift")
    x11.key_down("A")
    x11.key_up("shift")

    assert x11._keycode_is_down(keymap, shift_code)
    assert "shift" not in x11._held_keys
    assert x11._owns_implicit_shift

    x11.key_up("A")

    assert not x11._keycode_is_down(keymap, shift_code)
    assert events == [
        (X.KeyPress, shift_code),
        (X.KeyPress, a_code),
        (X.KeyRelease, a_code),
        (X.KeyRelease, shift_code),
    ]


def test_failed_shift_transfer_preserves_explicit_ownership(monkeypatch):
    expected, keymap, _events = fake_injection_display(monkeypatch)
    shift_code = expected["shift"][0]
    x11.key_down("shift")
    x11.key_down("A")
    flush_error = OSError("flush failed")
    x11._display.flush = lambda: (_ for _ in ()).throw(flush_error)

    with pytest.raises(OSError) as caught:
        x11.key_up("shift")

    assert caught.value is flush_error
    assert x11._keycode_is_down(keymap, shift_code)
    assert "shift" in x11._held_keys
    assert not x11._owns_implicit_shift


def test_scroll_release_failure_remains_recoverable(monkeypatch):
    display, _expected = active_us_keymap()
    display.flush = lambda: None
    monkeypatch.setattr(x11, "_display", display)
    monkeypatch.setattr(x11, "_root", object())
    release_error = OSError("wheel release failed")
    events = []

    def fail_release(_display, event_type, detail=0, **_kwargs):
        events.append((event_type, detail))
        if event_type == X.ButtonRelease:
            raise release_error

    monkeypatch.setattr(x11.xtest, "fake_input", fail_release)

    with pytest.raises(OSError) as caught:
        x11.scroll(1)

    assert caught.value is release_error
    assert 4 in x11._held_buttons

    monkeypatch.setattr(
        x11.xtest,
        "fake_input",
        lambda _display, event_type, detail=0, **_kwargs: events.append(
            (event_type, detail)
        ),
    )
    x11.release_all()

    assert 4 not in x11._held_buttons
    assert events[-1] == (X.ButtonRelease, 4)
