import sys
from importlib import import_module


if sys.platform == "win32":
    _BACKEND_MODULE = "my_model_arch.cpu_fast.desktop.win32"
elif sys.platform.startswith("linux"):
    _BACKEND_MODULE = "my_model_arch.cpu_fast.desktop.x11"
else:
    raise RuntimeError(f"NeuGaze does not support desktop platform {sys.platform!r}")

_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        _backend = import_module(_BACKEND_MODULE)
    return _backend


def initialize():
    return _get_backend().initialize()


def close():
    global _backend
    if _backend is not None:
        _backend.close()
        _backend = None


def get_screen_size():
    return _get_backend().get_screen_size()


def get_pointer_position():
    return _get_backend().get_pointer_position()


def move_pointer(x, y, relative=False):
    return _get_backend().move_pointer(x, y, relative=relative)


def key_down(key):
    return _get_backend().key_down(key)


def key_up(key):
    return _get_backend().key_up(key)


def is_key_down(key):
    return _get_backend().is_key_down(key)


def are_keys_down(keys):
    return _get_backend().are_keys_down(keys)


def supports_key(key):
    return _get_backend().supports_key(key)


def scroll(steps):
    return _get_backend().scroll(steps)


def is_cursor_visible():
    return _get_backend().is_cursor_visible()


def release_all():
    return _get_backend().release_all()
