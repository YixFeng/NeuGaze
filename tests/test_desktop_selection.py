import ctypes
import importlib.util
import sys
from pathlib import Path
from threading import Event, Thread
from types import ModuleType, SimpleNamespace

import pytest


SELECTOR_PATH = (
    Path(__file__).parents[1]
    / "my_model_arch"
    / "cpu_fast"
    / "desktop"
    / "__init__.py"
)


def _load_selector(monkeypatch, platform):
    monkeypatch.setattr(sys, "platform", platform)
    spec = importlib.util.spec_from_file_location(
        f"_desktop_selector_{platform.replace('-', '_')}", SELECTOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_win32_backend(monkeypatch, keybd_event):
    class FakeWin32Con(ModuleType):
        def __init__(self):
            super().__init__("win32con")
            self._values = {}

        def __getattr__(self, name):
            return self._values.setdefault(name, len(self._values) + 1)

    win32con = FakeWin32Con()
    win32api = ModuleType("win32api")
    win32api.keybd_event = keybd_event
    win32api.mouse_event = lambda *args: None
    win32api.GetAsyncKeyState = lambda key: 0
    win32api.GetSystemMetrics = lambda index: (1920, 1080)[index]
    win32api.GetCursorPos = lambda: (0, 0)
    win32api.SetCursorPos = lambda position: None
    win32gui = ModuleType("win32gui")
    win32gui.GetDC = lambda hwnd: 1
    win32gui.ReleaseDC = lambda hwnd, dc: 1
    win32print = ModuleType("win32print")
    win32print.GetDeviceCaps = lambda dc, index: (
        1920 if index == win32con.DESKTOPHORZRES else 1080
    )

    get_cursor_info = lambda cursor_info: True
    user32 = SimpleNamespace(GetCursorInfo=get_cursor_info)
    monkeypatch.setitem(sys.modules, "win32api", win32api)
    monkeypatch.setitem(sys.modules, "win32con", win32con)
    monkeypatch.setitem(sys.modules, "win32gui", win32gui)
    monkeypatch.setitem(sys.modules, "win32print", win32print)
    monkeypatch.setattr(
        ctypes, "WinDLL", lambda *args, **kwargs: user32, raising=False
    )

    backend_path = SELECTOR_PATH.with_name("win32.py")
    spec = importlib.util.spec_from_file_location(
        f"_desktop_win32_{id(keybd_event)}", backend_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("platform", "backend_name"),
    [
        ("win32", "my_model_arch.cpu_fast.desktop.win32"),
        ("linux", "my_model_arch.cpu_fast.desktop.x11"),
    ],
)
def test_selector_lazily_exports_only_selected_backend(
    monkeypatch, platform, backend_name
):
    desktop = _load_selector(monkeypatch, platform)
    calls = []

    def operation(name):
        def invoke(*args, **kwargs):
            calls.append((name, args, kwargs))
            return name

        return invoke

    backend = SimpleNamespace(
        initialize=operation("initialize"),
        close=operation("close"),
        get_screen_size=operation("get_screen_size"),
        get_pointer_position=operation("get_pointer_position"),
        move_pointer=operation("move_pointer"),
        key_down=operation("key_down"),
        key_up=operation("key_up"),
        key_up_owned=operation("key_up_owned"),
        is_key_down=operation("is_key_down"),
        are_keys_down=operation("are_keys_down"),
        supports_key=operation("supports_key"),
        scroll=operation("scroll"),
        is_cursor_visible=operation("is_cursor_visible"),
        release_all=operation("release_all"),
    )
    imported = []

    def import_backend(name):
        imported.append(name)
        assert name == backend_name
        return backend

    monkeypatch.setattr(desktop, "import_module", import_backend)

    assert desktop._backend is None
    assert imported == []
    assert desktop.initialize() == "initialize"
    assert desktop.get_screen_size() == "get_screen_size"
    assert desktop.get_pointer_position() == "get_pointer_position"
    assert desktop.move_pointer(3, 4, relative=True) == "move_pointer"
    assert desktop.key_down("w") == "key_down"
    assert desktop.key_up("w") == "key_up"
    assert desktop.key_up_owned("w") == "key_up_owned"
    assert desktop.is_key_down("w") == "is_key_down"
    assert desktop.are_keys_down(("esc", "q")) == "are_keys_down"
    assert desktop.supports_key("w") == "supports_key"
    assert desktop.scroll(-2) == "scroll"
    assert desktop.is_cursor_visible() == "is_cursor_visible"
    assert desktop.release_all() == "release_all"

    assert imported == [backend_name]
    assert ("move_pointer", (3, 4), {"relative": True}) in calls
    desktop.close()
    assert calls[-1] == ("close", (), {})
    assert desktop._backend is None

    desktop.close()
    assert imported == [backend_name]
    assert calls.count(("close", (), {})) == 1


def test_selector_rejects_unsupported_platform_immediately(monkeypatch):
    with pytest.raises(
        RuntimeError, match="NeuGaze does not support desktop platform 'darwin'"
    ):
        _load_selector(monkeypatch, "darwin")


def test_selector_close_waits_for_dispatched_operation(monkeypatch):
    desktop = _load_selector(monkeypatch, "linux")
    operation_started = Event()
    allow_operation_to_finish = Event()
    close_started = Event()
    operation_errors = []

    def key_down(key):
        operation_started.set()
        if not allow_operation_to_finish.wait(1):
            raise TimeoutError("test did not release key_down")

    backend = SimpleNamespace(
        key_down=key_down,
        close=lambda: close_started.set(),
    )
    monkeypatch.setattr(desktop, "import_module", lambda name: backend)

    def record_error(operation):
        try:
            operation()
        except Exception as error:
            operation_errors.append(error)

    key_thread = Thread(
        target=record_error, args=(lambda: desktop.key_down("w"),)
    )
    key_thread.start()
    assert operation_started.wait(1)

    close_thread = Thread(target=record_error, args=(desktop.close,))
    close_thread.start()
    close_overlapped_operation = close_started.wait(0.1)

    allow_operation_to_finish.set()
    key_thread.join(1)
    close_thread.join(1)

    assert not close_overlapped_operation
    assert not key_thread.is_alive()
    assert not close_thread.is_alive()
    assert operation_errors == []
    assert close_started.is_set()
    assert desktop._backend is None


def test_selector_import_failure_remains_retryable(monkeypatch):
    desktop = _load_selector(monkeypatch, "linux")
    import_error = ModuleNotFoundError("x11 dependency unavailable")
    backend = SimpleNamespace(initialize=lambda: "initialized")
    attempts = 0

    def import_backend(name):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise import_error
        return backend

    monkeypatch.setattr(desktop, "import_module", import_backend)

    with pytest.raises(ModuleNotFoundError) as caught:
        desktop.initialize()
    assert caught.value is import_error
    assert desktop._backend is None

    assert desktop.initialize() == "initialized"
    assert desktop._backend is backend
    assert attempts == 2


def test_selector_close_failure_remains_retryable(monkeypatch):
    desktop = _load_selector(monkeypatch, "linux")
    close_error = OSError("close failed")
    close_attempts = 0

    def close():
        nonlocal close_attempts
        close_attempts += 1
        if close_attempts == 1:
            raise close_error

    backend = SimpleNamespace(initialize=lambda: None, close=close)
    monkeypatch.setattr(desktop, "import_module", lambda name: backend)
    desktop.initialize()

    with pytest.raises(OSError) as caught:
        desktop.close()
    assert caught.value is close_error
    assert desktop._backend is backend

    desktop.close()
    assert desktop._backend is None
    assert close_attempts == 2


def test_win32_release_all_serializes_injection_and_tracking(monkeypatch):
    injection_started = Event()
    allow_injection_to_finish = Event()
    cleanup_finished = Event()
    operation_errors = []
    injected_flags = []

    def keybd_event(vk, scan, flags, extra_info):
        injected_flags.append(flags)
        if flags == 0:
            injection_started.set()
            if not allow_injection_to_finish.wait(1):
                raise TimeoutError("test did not release key injection")

    backend = _load_win32_backend(monkeypatch, keybd_event)

    def record_error(operation, finished=None):
        try:
            operation()
        except Exception as error:
            operation_errors.append(error)
        finally:
            if finished is not None:
                finished.set()

    key_thread = Thread(
        target=record_error, args=(lambda: backend.key_down("w"),)
    )
    key_thread.start()
    assert injection_started.wait(1)

    cleanup_thread = Thread(
        target=record_error, args=(backend.release_all, cleanup_finished)
    )
    cleanup_thread.start()
    cleanup_missed_in_flight_injection = cleanup_finished.wait(0.1)

    allow_injection_to_finish.set()
    key_thread.join(1)
    cleanup_thread.join(1)

    assert not cleanup_missed_in_flight_injection
    assert not key_thread.is_alive()
    assert not cleanup_thread.is_alive()
    assert operation_errors == []
    assert injected_flags == [0, backend.win32con.KEYEVENTF_KEYUP]
    assert backend._held_inputs == set()



def test_win32_screen_size_uses_desktop_device_caps_and_releases_dc(
    monkeypatch,
):
    backend = _load_win32_backend(monkeypatch, lambda *args: None)
    calls = []
    backend.win32api.GetSystemMetrics = lambda index: pytest.fail(
        "GetSystemMetrics fallback is forbidden"
    )
    backend.win32gui.GetDC = (
        lambda hwnd: calls.append(("get_dc", hwnd)) or 77
    )
    backend.win32gui.ReleaseDC = (
        lambda hwnd, dc: calls.append(("release_dc", hwnd, dc)) or 1
    )
    backend.win32print.GetDeviceCaps = (
        lambda dc, index: calls.append(("caps", dc, index))
        or {
            backend.win32con.DESKTOPHORZRES: 2560,
            backend.win32con.DESKTOPVERTRES: 1440,
        }[index]
    )

    assert backend.get_screen_size() == (2560, 1440)
    assert calls == [
        ("get_dc", 0),
        ("caps", 77, backend.win32con.DESKTOPHORZRES),
        ("caps", 77, backend.win32con.DESKTOPVERTRES),
        ("release_dc", 0, 77),
    ]


def test_win32_key_up_owned_releases_only_recorded_input(monkeypatch):
    calls = []
    backend = _load_win32_backend(
        monkeypatch,
        lambda vk, scan, flags, extra: calls.append(
            (vk, scan, flags, extra)
        ),
    )
    backend._held_inputs.clear()

    assert backend.key_up_owned("w") is False
    assert calls == []

    backend._held_inputs.add("w")
    assert backend.key_up_owned("w") is True
    assert len(calls) == 1
    assert calls[0][2] == backend.win32con.KEYEVENTF_KEYUP
    assert "w" not in backend._held_inputs


def test_win32_key_up_owned_failure_retains_ownership(monkeypatch):
    source_error = OSError("Win32 release failed")

    def fail_release(vk, scan, flags, extra):
        raise source_error

    backend = _load_win32_backend(monkeypatch, fail_release)
    backend._held_inputs.clear()
    backend._held_inputs.add("w")

    with pytest.raises(OSError) as caught:
        backend.key_up_owned("w")

    assert caught.value is source_error
    assert "w" in backend._held_inputs
