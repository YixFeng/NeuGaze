import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from Xlib import X

from my_model_arch.cpu_fast.desktop import x11


pytestmark = pytest.mark.x11
TRUSTED_XVFB = shutil.which("Xvfb")


def xvfb_process_matches(
    display,
    authority,
    proc_root=Path("/proc"),
    uid=None,
    trusted_executable=None,
):
    if uid is None:
        uid = os.getuid()
    if trusted_executable is None:
        trusted_executable = TRUSTED_XVFB
    if trusted_executable is None:
        return False
    try:
        processes = tuple(proc_root.iterdir())
    except OSError:
        return False
    for process in processes:
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != uid:
                continue
            arguments = [
                field.decode()
                for field in (process / "cmdline").read_bytes().split(b"\0")
                if field
            ]
            executable_matches = os.path.samefile(
                process / "exe",
                trusted_executable,
            )
        except (OSError, UnicodeDecodeError):
            continue
        if (
            not executable_matches
            or len(arguments) < 2
            or arguments[1] != display
            or arguments.count("-auth") != 1
        ):
            continue
        auth_index = arguments.index("-auth")
        if (
            auth_index + 1 < len(arguments)
            and arguments[auth_index + 1] == str(authority)
        ):
            return True
    return False


def require_isolated_display(proc_root=Path("/proc"), uid=None):
    if uid is None:
        uid = os.getuid()
    display = os.environ.get("DISPLAY")
    authority_value = os.environ.get("XAUTHORITY")
    if (
        not display
        or not display.startswith(":")
        or not display[1:].isdigit()
        or str(int(display[1:])) != display[1:]
        or not authority_value
    ):
        pytest.fail("X11 integration tests require a local xvfb-run display")

    authority = Path(authority_value)
    try:
        valid_authority = (
            authority.is_absolute()
            and authority.is_file()
            and authority.stat().st_uid == uid
        )
    except OSError:
        valid_authority = False
    if not valid_authority or not xvfb_process_matches(
        display,
        authority,
        proc_root=proc_root,
        uid=uid,
    ):
        pytest.fail(
            "X11 injection tests require the exact local Xvfb server "
            "created by xvfb-run"
        )


@pytest.fixture
def controlled_proc(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()

    def add_process(pid, arguments, executable="/usr/bin/Xvfb"):
        process = proc_root / str(pid)
        process.mkdir()
        (process / "cmdline").write_bytes(
            b"\0".join(os.fsencode(argument) for argument in arguments) + b"\0"
        )
        (process / "exe").symlink_to(executable)

    return proc_root, add_process


def test_xvfb_process_match_requires_exact_controlled_process(
    controlled_proc,
    tmp_path,
):
    proc_root, add_process = controlled_proc
    trusted_xvfb = tmp_path / "trusted" / "Xvfb"
    trusted_xvfb.parent.mkdir()
    trusted_xvfb.write_bytes(b"trusted")
    authority = tmp_path / "Xauthority"
    authority.write_bytes(b"test")
    add_process(
        100,
        ["Xvfb", ":77", "-screen", "0", "1280x720x24", "-auth", str(authority)],
        executable=trusted_xvfb,
    )

    assert xvfb_process_matches(
        ":77",
        authority,
        proc_root=proc_root,
        uid=os.getuid(),
        trusted_executable=trusted_xvfb,
    )
    assert not xvfb_process_matches(
        ":78",
        authority,
        proc_root=proc_root,
        uid=os.getuid(),
        trusted_executable=trusted_xvfb,
    )
    assert not xvfb_process_matches(
        ":77",
        tmp_path / "other-authority",
        proc_root=proc_root,
        uid=os.getuid(),
        trusted_executable=trusted_xvfb,
    )


def test_xvfb_process_match_rejects_different_inode_named_xvfb(
    controlled_proc,
    tmp_path,
):
    proc_root, add_process = controlled_proc
    trusted_xvfb = tmp_path / "trusted" / "Xvfb"
    trusted_xvfb.parent.mkdir()
    trusted_xvfb.write_bytes(b"trusted")
    copied_xvfb = tmp_path / "copied" / "Xvfb"
    copied_xvfb.parent.mkdir()
    copied_xvfb.write_bytes(trusted_xvfb.read_bytes())
    authority = tmp_path / "Xauthority"
    authority.write_bytes(b"test")
    add_process(
        101,
        ["Xvfb", ":78", "-auth", str(authority)],
        executable=copied_xvfb,
    )

    assert not xvfb_process_matches(
        ":78",
        authority,
        proc_root=proc_root,
        uid=os.getuid(),
        trusted_executable=trusted_xvfb,
    )


@pytest.mark.parametrize("display", (":0", ":1.0", "unix/:1", ":2"))
def test_isolation_guard_rejects_live_display_aliases(monkeypatch, display):
    monkeypatch.setenv("DISPLAY", display)
    monkeypatch.setenv("XAUTHORITY", "/home/user/.Xauthority")

    with pytest.raises(pytest.fail.Exception, match="xvfb-run"):
        require_isolated_display()


@pytest.fixture
def backend(monkeypatch):
    require_isolated_display()
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    x11.initialize()
    try:
        yield
    finally:
        x11.close()


def test_initialize_and_close_lifecycle(monkeypatch):
    require_isolated_display()
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)

    x11.initialize()
    try:
        width, height = x11.get_screen_size()
        assert width > 0
        assert height > 0
    finally:
        x11.close()

    with pytest.raises(RuntimeError, match="initialize"):
        x11.get_screen_size()


def test_moves_and_queries_pointer_absolutely_and_relatively(backend):
    width, height = x11.get_screen_size()
    start_x = min(20, width - 1)
    start_y = min(30, height - 1)

    x11.move_pointer(start_x, start_y)
    assert x11.get_pointer_position() == (start_x, start_y)

    delta_x = 3 if start_x + 3 < width else -3
    delta_y = 4 if start_y + 4 < height else -4
    x11.move_pointer(delta_x, delta_y, relative=True)

    assert x11.get_pointer_position() == (
        start_x + delta_x,
        start_y + delta_y,
    )


def test_key_down_query_and_up(backend):
    assert x11.supports_key("a")

    x11.key_up("a")
    assert not x11.is_key_down("a")

    x11.key_down("a")
    assert x11.is_key_down("a")

    x11.key_up("a")
    assert not x11.is_key_down("a")


def make_pointer_event_window():
    display = x11._display
    root = x11._root
    window = root.create_window(
        0,
        0,
        100,
        100,
        0,
        X.CopyFromParent,
        X.InputOutput,
        X.CopyFromParent,
        event_mask=X.ButtonPressMask | X.ButtonReleaseMask,
    )
    window.map()
    display.sync()
    x11.move_pointer(10, 10)
    display.sync()
    while display.pending_events():
        display.next_event()
    return window


def pointer_button_events():
    display = x11._display
    display.sync()
    events = []
    while display.pending_events():
        event = display.next_event()
        if event.type in (X.ButtonPress, X.ButtonRelease):
            events.append((event.type, event.detail))
    return events


def test_button_press_release_and_side_buttons(backend):
    window = make_pointer_event_window()
    try:
        x11.key_down("mouse_left")
        assert x11.is_key_down("mouse_left")
        x11.key_up("mouse_left")
        assert not x11.is_key_down("mouse_left")

        x11.key_down("mouse_middle")
        x11.key_up("mouse_middle")
        x11.key_down("mouse_right")
        x11.key_up("mouse_right")
        x11.key_down("mouse_x1")
        x11.key_up("mouse_x1")
        x11.key_down("mouse_x2")
        x11.key_up("mouse_x2")

        assert pointer_button_events() == [
            (X.ButtonPress, 1),
            (X.ButtonRelease, 1),
            (X.ButtonPress, 2),
            (X.ButtonRelease, 2),
            (X.ButtonPress, 3),
            (X.ButtonRelease, 3),
            (X.ButtonPress, 8),
            (X.ButtonRelease, 8),
            (X.ButtonPress, 9),
            (X.ButtonRelease, 9),
        ]
    finally:
        window.destroy()
        x11._display.flush()


def test_scroll_emits_press_and_release_for_each_step(backend):
    window = make_pointer_event_window()
    try:
        x11.scroll(2)
        x11.scroll(-1)

        assert pointer_button_events() == [
            (X.ButtonPress, 4),
            (X.ButtonRelease, 4),
            (X.ButtonPress, 4),
            (X.ButtonRelease, 4),
            (X.ButtonPress, 5),
            (X.ButtonRelease, 5),
        ]
    finally:
        window.destroy()
        x11._display.flush()


def test_unknown_key_reports_name_and_display(backend):
    assert not x11.supports_key("not_a_real_key")

    with pytest.raises(ValueError) as caught:
        x11.key_down("not_a_real_key")

    assert "not_a_real_key" in str(caught.value)
    assert os.environ["DISPLAY"] in str(caught.value)


def test_wayland_is_rejected_in_subprocess():
    require_isolated_display()
    environment = os.environ.copy()
    environment["XDG_SESSION_TYPE"] = "wayland"

    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from my_model_arch.cpu_fast.desktop.x11 "
                "import initialize; initialize()"
            ),
        ],
        cwd=os.getcwd(),
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "wayland" in completed.stderr


def test_isolation_guard_rejects_forged_xvfb_path_before_connect(
    monkeypatch,
    tmp_path,
    controlled_proc,
):
    proc_root, _add_process = controlled_proc
    authority_dir = tmp_path / "xvfb-run.fake"
    authority_dir.mkdir()
    authority = authority_dir / "Xauthority"
    authority.write_bytes(b"forged")
    monkeypatch.setenv("DISPLAY", ":1")
    monkeypatch.setenv("XAUTHORITY", str(authority))
    connected = False

    def connect(_name):
        nonlocal connected
        connected = True

    monkeypatch.setattr(x11.xdisplay, "Display", connect)

    with pytest.raises(pytest.fail.Exception, match="xvfb-run"):
        require_isolated_display(proc_root=proc_root, uid=os.getuid())

    assert not connected
