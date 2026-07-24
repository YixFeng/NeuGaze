import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

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
