import json
import os
import select
import socket
import subprocess

import pytest
from conftest import SCRIPTS

LANG_SH = os.path.join(SCRIPTS, "lang.sh")
SIGNATURE = "test-instance"


class Desk:
    """lang.sh against a fake `hyprctl` and a fake Hyprland event socket."""

    def __init__(self, tmp):
        self.keymap_file = tmp / "keymap"
        self.set_keymap("English (US)")
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        hyprctl = bin_dir / "hyprctl"
        hyprctl.write_text(f'#!/bin/sh\ncat "{self.keymap_file}"\n')
        hyprctl.chmod(0o755)
        sock_dir = tmp / "hypr" / SIGNATURE
        sock_dir.mkdir(parents=True)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(sock_dir / ".socket2.sock"))
        self.server.listen()
        self.server.settimeout(5)
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                   XDG_RUNTIME_DIR=str(tmp), HYPRLAND_INSTANCE_SIGNATURE=SIGNATURE)
        self.proc = subprocess.Popen([LANG_SH], stdout=subprocess.PIPE, env=env, text=True,
                                     start_new_session=True)
        assert self.proc.stdout is not None
        self.out = self.proc.stdout
        self.conn = socket.socket()   # replaced by the connection lang.sh opens

    def set_keymap(self, keymap):
        devices = {"keyboards": [
            {"name": "power-button", "main": False, "active_keymap": "Persian"},
            {"name": "at-keyboard", "main": True, "active_keymap": keymap},
        ]}
        self.keymap_file.write_text(json.dumps(devices))

    def accept(self):
        self.conn.close()
        self.conn, _ = self.server.accept()

    def send(self, *events):
        self.conn.sendall("".join(e + "\n" for e in events).encode())

    def line(self, timeout=3):
        """The next line lang.sh prints, or None when it prints nothing in time."""
        ready, _, _ = select.select([self.out], [], [], timeout)
        return self.out.readline().strip() if ready else None

    def close(self):
        os.killpg(self.proc.pid, 9)
        self.proc.wait()
        self.conn.close()
        self.server.close()


@pytest.fixture
def desk(tmp_path):
    d = Desk(tmp_path)
    yield d
    d.close()


def test_prints_layout_at_start(desk):
    """LSES-1: Given the main keyboard on English, when lang.sh starts, then it prints EN before any event."""
    assert desk.line() == "EN"


def test_prints_new_layout_on_activelayout_event(desk):
    """LSES-2: Given lang.sh showing EN, when an activelayout event follows a switch to Persian, then it prints FA."""
    desk.accept()
    assert desk.line() == "EN"
    desk.set_keymap("Persian")
    desk.send("activelayout>>at-keyboard,Persian")
    assert desk.line() == "FA"


def test_prints_nothing_for_events_that_do_not_change_layout(desk):
    """LSES-3: Given lang.sh showing EN, when other events or a same-layout activelayout arrive, then it prints nothing."""
    desk.accept()
    assert desk.line() == "EN"
    desk.send("workspace>>2", "activewindow>>kitty,fish", "activelayout>>at-keyboard,English (US)")
    assert desk.line(timeout=1) is None


def test_reconnects_after_socket_closes(desk):
    """LSES-4: Given the event socket closes, when lang.sh connects again and the layout changes, then it prints FA."""
    desk.accept()
    assert desk.line() == "EN"
    desk.conn.close()
    desk.accept()
    desk.set_keymap("Persian")
    desk.send("activelayout>>at-keyboard,Persian")
    assert desk.line() == "FA"
