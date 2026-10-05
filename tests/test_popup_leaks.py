"""Popups give back the memory of the rows they remove (spec LEAK). A row whose
signal handlers hold the row itself is a cycle PyGObject never frees: the
clipboard grew 17.6 MB and the picker 5.2 MB on every open. These tests build the
real row widgets, so they need a display; without one they are skipped."""

import gc
import os
import subprocess
import sys
import time
import weakref

import gi
import panel
import pytest
from conftest import SCRIPTS

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib, Gtk

needs_display = pytest.mark.skipif(not Gtk.init_check(), reason="needs a display")


def picture(path, width, height):
    GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, width, height).savev(
        str(path), "png", [], []
    )
    return str(path)


def alive_after_removal(container, make, count=6):
    """Put `count` rows made by make() in the container, remove them, run the
    main loop and the garbage collector; return how many are still alive."""
    refs = []
    for i in range(count):
        row = make(i)
        container.append(row)
        refs.append(weakref.ref(row))
    del row
    while (child := container.get_first_child()) is not None:
        container.remove(child)
    del child
    while GLib.MainContext.default().iteration(False):
        pass
    gc.collect()
    return sum(r() is not None for r in refs)


class FakeClipboardApp:
    def toggle_pin(self, row):
        pass

    def delete(self, row):
        pass

    def copy_only(self, row):
        pass


@needs_display
def test_removed_clipboard_rows_are_freed(tmp_path):
    """LEAK-1: given the clipboard list holds text rows and picture rows, when
    they are removed (every open fills the list again), then every removed Item
    is freed."""
    cb = panel.load("clipboard")
    app = FakeClipboardApp()
    img = picture(tmp_path / "shot.png", 895, 686)

    def make(i):
        if i % 2:
            return cb.Item(app, f"text {i}", line=f"{i}\ttext {i}", cid=str(i))
        return cb.Item(
            app, "[[ binary data 60 KiB png 895x686 ]]", pinned=True, image=img
        )

    assert alive_after_removal(Gtk.ListBox(), make) == 0


class FakePickerApp:
    def __init__(self):
        self.textures = {}

    def window_icon(self, client):
        return Gio.ThemedIcon.new("application-x-executable")

    def close_window(self, card):
        pass


@needs_display
def test_removed_picker_cards_are_freed():
    """LEAK-2: given the picker grid holds cards, when they are dropped (on
    close, or when the grid is drawn again), then every removed Card is freed."""
    mp = panel.load("minimized-picker")
    app = FakePickerApp()

    def make(i):
        client = {
            "address": f"0x{i}",
            "title": f"win {i}",
            "class": "kitty",
            "workspace": {"name": "special:minimized"},
        }
        return mp.Card(app, client, i + 1)

    assert alive_after_removal(Gtk.FlowBox(), make) == 0


@needs_display
def test_clipboard_thumbnails_are_decoded_small(tmp_path):
    """LEAK-3: given a picture taller than 180 px, when the clipboard shows it,
    then the texture is at most 180 px tall with the picture's aspect ratio;
    given a small picture, then it keeps its own size."""
    cb = panel.load("clipboard")
    big = cb.thumbnail(picture(tmp_path / "big.png", 895, 686))
    assert big.get_height() <= 180
    assert abs(big.get_width() / big.get_height() - 895 / 686) < 0.02
    tall = cb.thumbnail(picture(tmp_path / "tall.png", 449, 1199))
    assert tall.get_height() <= 180
    small = cb.thumbnail(picture(tmp_path / "small.png", 48, 52))
    assert (small.get_width(), small.get_height()) == (48, 52)


def test_restart_stops_hidden_popups_whose_script_is_gone(tmp_path):
    """LEAK-4: given a hidden popup whose script was removed and a hidden process
    whose script still exists but is in no list (like Settings), when
    `popup.sh --restart` runs, then the first stops and the second keeps running,
    and the list of the twelve popups is still there (the sweep is an addition)."""
    with open(os.path.join(SCRIPTS, "popup.sh"), encoding="utf-8") as f:
        listed = f.read().split('all="', 1)[1].split('"', 1)[0].split()
    assert len(listed) == 12
    scripts = tmp_path / ".config" / "waybar" / "scripts"
    scripts.mkdir(parents=True)
    procs = {}
    for name in ("ghost-popup", "settings"):
        path = scripts / f"{name}.py"
        path.write_text("import time\ntime.sleep(60)\n")
        procs[name] = subprocess.Popen([sys.executable, str(path), "--hidden"])
    try:
        time.sleep(0.2)
        (scripts / "ghost-popup.py").unlink()
        runtime = tmp_path / "run"
        runtime.mkdir()
        env = dict(os.environ, HOME=str(tmp_path), XDG_RUNTIME_DIR=str(runtime))
        subprocess.run(
            ["bash", os.path.join(SCRIPTS, "popup.sh"), "--restart"],
            env=env,
            timeout=20,
            check=True,
        )
        assert procs["ghost-popup"].wait(timeout=5) is not None
        assert procs["settings"].poll() is None
    finally:
        for p in procs.values():
            p.kill()
            p.wait()
