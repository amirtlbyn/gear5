"""SUPER+SHIFT+Escape runs `popup.sh --unstick` (spec UNSTICK): it kills an open
popup that hangs and keeps the keyboard, and starts it again hidden. These tests
run popup.sh with HOME in a temporary folder, stub popup scripts there, and a fake
`hyprctl` that lists the layers we choose."""

import json
import os
import re
import signal
import subprocess
import time

import pytest
from conftest import ROOT, SCRIPTS

POPUP_SH = os.path.join(SCRIPTS, "popup.sh")
STUB = """#!/usr/bin/env python3
import os, sys, time
with open(os.path.join(os.environ["HOME"], "started.log"), "a") as log:
    log.write(f"{os.getpid()} {sys.argv[1:]!r}\\n")
time.sleep(60)
"""


def gone(pid):
    try:
        with open(f"/proc/{pid}/stat") as stat:
            return stat.read().rsplit(")", 1)[1].split()[0] == "Z"
    except FileNotFoundError:
        return True


class Desktop:
    """popup.sh's view of a desktop: stub popups, their marks, and a fake hyprctl."""

    def __init__(self, tmp):
        self.home = tmp / "home"
        self.scripts = self.home / ".config" / "waybar" / "scripts"
        self.scripts.mkdir(parents=True)
        for name in ("calculator", "launcher", "settings"):
            stub = self.scripts / f"{name}.py"
            stub.write_text(STUB)
            stub.chmod(0o755)
        self.marks = tmp / "run" / "popups"
        self.marks.mkdir(parents=True)
        self.layers_file = tmp / "layers.json"
        bin_dir = tmp / "bin"
        bin_dir.mkdir()
        hyprctl = bin_dir / "hyprctl"
        hyprctl.write_text(f'#!/bin/sh\ncat "{self.layers_file}"\n')
        hyprctl.chmod(0o755)
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            XDG_RUNTIME_DIR=str(tmp / "run"),
            PATH=f"{bin_dir}:{os.environ['PATH']}",
        )
        self.pids = []

    def start(self, *argv):
        """Start a process the way popup.sh does (setsid, in the background), so it
        is not our child and nothing here has to reap it; return its pid."""
        out = subprocess.run(
            ["bash", "-c", 'setsid "$@" >/dev/null 2>&1 & echo $!', "start", *argv],
            env=self.env, capture_output=True, text=True, check=True,
        ).stdout
        pid = int(out)
        self.pids.append(pid)
        return pid

    def start_popup(self, name):
        pid = self.start(str(self.scripts / f"{name}.py"), "zoro", "--hidden")
        self.wait_started(pid)
        return pid

    def started(self):
        log = self.home / "started.log"
        lines = log.read_text().splitlines() if log.exists() else []
        return {int(pid): args for pid, args in (line.split(" ", 1) for line in lines)}

    def wait_started(self, pid, timeout=5):
        end = time.monotonic() + timeout
        while pid not in self.started() and time.monotonic() < end:
            time.sleep(0.02)
        return pid in self.started()

    def wait_new(self, known, timeout=5):
        """The pids started since `known`, once there is one (or after timeout)."""
        end = time.monotonic() + timeout
        while not (new := set(self.started()) - set(known)) and time.monotonic() < end:
            time.sleep(0.02)
        return new

    def show_layers(self, pids):
        levels = {"2": [{"namespace": "waybar", "pid": pid} for pid in pids]}
        self.layers_file.write_text(json.dumps({"eDP-1": {"levels": levels}}))

    def unstick(self):
        began = time.monotonic()
        subprocess.run([POPUP_SH, "--unstick"], env=self.env, check=True, timeout=10)
        return time.monotonic() - began

    def cleanup(self):
        for pid in self.pids + list(self.started()):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.fixture
def desk(tmp_path):
    d = Desktop(tmp_path)
    yield d
    d.cleanup()


@pytest.fixture
def stuck(desk):
    """A calculator open on a screen and paused, with its open mark."""
    pid = desk.start_popup("calculator")
    os.kill(pid, signal.SIGSTOP)
    (desk.marks / "io.local.calculator").touch()
    desk.show_layers([pid])
    return pid


def test_the_keybind_runs_unstick():
    """UNSTICK-1: given hyprland.lua, when its binds are read, then
    SUPER+SHIFT+Escape runs `popup.sh --unstick`, and no other bind uses that key."""
    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    uses = re.findall(r'bind\(mainMod \.\. " \+ SHIFT \+ Escape",\s*(.*)\)\n', lua)
    assert uses == ['exec("~/.config/waybar/scripts/popup.sh --unstick")']


def test_a_paused_open_popup_is_killed_and_its_mark_removed(desk, stuck):
    """UNSTICK-2: given a calculator that has a layer on a screen and is paused
    with SIGSTOP, when `popup.sh --unstick` runs, then within 2 s its process is
    gone and its mark in $XDG_RUNTIME_DIR/popups is removed."""
    took = desk.unstick()

    assert gone(stuck)
    assert took <= 2
    assert not (desk.marks / "io.local.calculator").exists()


def test_the_killed_popup_starts_again_hidden_with_the_theme_in_use(desk, stuck):
    """UNSTICK-3: given the paused calculator, when `popup.sh --unstick` has
    killed it, then a new calculator process runs with no theme argument (the
    theme in use) and --hidden."""
    desk.unstick()

    new = desk.wait_new([stuck])
    assert len(new) == 1
    (pid,) = new
    assert desk.started()[pid] == "['', '--hidden']"
    assert not gone(pid)


def test_it_signals_nothing_that_is_not_an_open_popup(desk):
    """UNSTICK-4: given a hidden launcher (no layer), a layer of a process that
    is not ours (the bar), and a layer of a script in the popup folder that is
    not a popup (settings.py), when `popup.sh --unstick` runs, then none of them
    gets a signal and no popup is started."""
    hidden = desk.start_popup("launcher")
    bar = desk.start("sleep", "60")
    settings = desk.start_popup("settings")
    for pid in (hidden, settings):
        os.kill(pid, signal.SIGSTOP)
    desk.show_layers([bar, settings])

    desk.unstick()

    assert not desk.wait_new([hidden, settings], timeout=1)
    assert not any(gone(pid) for pid in (hidden, bar, settings))
