"""The overview on SUPER+Tab (spec OVERVIEW): desk rows, filter, number keys,
the window address gate, and nothing kept after a close. The tests that build
the real widgets need a display; without one they are skipped. They never show
the window, run hyprctl, or capture a real window."""

import gc
import os
import re
import weakref

import gi
import panel
import pytest
from conftest import ROOT, SCRIPTS

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

mod = panel.load("overview")
import scrolling  # noqa: E402
needs_display = pytest.mark.skipif(not Gtk.init_check(), reason="needs a display")

MONITORS = [
    {"id": 0, "name": "DP-1", "x": 0, "focused": True, "activeWorkspace": {"id": 22}},
    {"id": 1, "name": "HDMI-A-1", "x": 1080, "focused": False, "activeWorkspace": {"id": 12}},
]


def win(address, ws_id, monitor=0, at=(0, 0), title="t", cls="kitty", ws_name=None):
    return {
        "address": address, "title": title, "class": cls, "monitor": monitor, "at": list(at),
        "mapped": True, "workspace": {"id": ws_id, "name": ws_name or str(ws_id)},
    }


CLIENTS = [
    win("0xa", 12, monitor=1, at=(1100, 500), title="chrome", cls="google-chrome"),
    win("0xb", 20, monitor=1, at=(1100, 500), title="notes"),  # desk 10
    win("0xc", 21, monitor=0, at=(0, 900), title="kitty low"),  # desk 1, lower
    win("0xd", 11, monitor=1, at=(1100, 400), title="kitty right screen"),  # desk 1, right screen
    win("0xe", 21, monitor=0, at=(0, 100), title="kitty top"),  # desk 1, upper
    win("0xf", -98, at=(5, 5), title="Telegram", cls="telegram", ws_name="special:minimized"),
    win("0x10", -99, title="scratch", ws_name="special:scratch"),  # another special desk
    {**win("0x11", 13, title="unmapped"), "mapped": False},
]


def rows_as_addresses(rows):
    return [(d, [c["address"] for c in wins]) for d, wins in rows]


def test_the_keybinds():
    """OVERVIEW-1: given hyprland.lua, when its binds are read, then SUPER+Tab
    runs `popup.sh overview`, SUPER+SHIFT+G is "next window in group", and no
    other bind uses either key."""
    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    tab = re.findall(r'shortcut\("[a-z_.]+", "[^"]*", mainMod \.\. " \+ Tab",\s*(.*)\)\n', lua)
    group_next = re.findall(r'shortcut\("[a-z_.]+", "[^"]*", mainMod \.\. " \+ SHIFT \+ G",\s*(.*)\)\n', lua)
    assert tab == ['exec("~/.config/waybar/scripts/popup.sh overview")']
    assert group_next == ["hl.dsp.group.next()"]
    assert lua.count("hl.dsp.group.next()") == 1


def test_one_row_per_desk_in_order_then_the_minimized_ones():
    """OVERVIEW-2: given windows on desks 1, 2 and 10 across two screens, a
    minimized one, one on another special desk and an unmapped one, and the
    current desk 2, when the rows are built, then they are desks 1, 2, 10 in
    order, then "min"; desk 1 goes left screen top to bottom, then the right
    screen; the scratchpad and unmapped windows are left out. An empty current
    desk still gets its (empty) row."""
    rows = mod.desk_rows(CLIENTS, MONITORS, mod.current_desk(MONITORS))

    assert mod.current_desk(MONITORS) == 2
    assert rows_as_addresses(rows) == [
        (1, ["0xe", "0xc", "0xd"]),
        (2, ["0xa"]),
        (10, ["0xb"]),
        ("min", ["0xf"]),
    ]
    assert rows_as_addresses(mod.desk_rows(CLIENTS[:1], MONITORS, 5)) == [(2, ["0xa"]), (5, [])]


def test_a_picked_window_goes_through_the_address_gate():
    """OVERVIEW-3: given a window address, when it is picked, then the command
    is `hyprctl eval goToWindow("<address>")`; an address that is not 0x + hex
    (text from a title, a quote) is refused before it reaches Hyprland; and
    hyprland.lua defines goToWindow, which restores a minimized window and
    otherwise switches every screen to the window's desk before it focuses it."""
    assert mod.go_cmd("0x5a1f") == ["hyprctl", "eval", 'goToWindow("0x5a1f")']
    for bad in ('0x1") os.execute("rm', "", None, "5a1f", "0xZZ"):
        with pytest.raises(ValueError):
            mod.go_cmd(bad)
    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    body = lua.split("function goToWindow(addr)", 1)[1].split("\nend\n", 1)[0]
    assert "restoreMinimized(addr)" in body
    assert body.index("showDesk(deskOf(w.workspace.id))") < body.index("hl.dsp.focus({ window = w })")


def test_number_keys_and_the_filter():
    """OVERVIEW-4: given the rows, when 1-9 or 0 is pressed, then it goes to
    desk 1-9 or 10 (`desk(n)`); when words are typed, only the windows with
    every word in their title or app stay, and rows left empty (the empty
    current desk too) are hidden; an empty filter keeps every row."""
    assert [mod.desk_for_digit(d) for d in (1, 5, 9, 0)] == [1, 5, 9, 10]
    assert mod.desk_cmd(10) == ["hyprctl", "eval", "desk(10)"]
    with pytest.raises(ValueError):
        mod.desk_cmd(11)
    rows = mod.desk_rows(CLIENTS, MONITORS, 3)  # desk 3 is empty
    assert rows_as_addresses(mod.filter_rows(rows, "KITTY top")) == [(1, ["0xe"])]
    assert rows_as_addresses(mod.filter_rows(rows, "tele")) == [("min", ["0xf"])]
    assert mod.filter_rows(rows, "  ") == rows


@pytest.fixture
def overview(monkeypatch):
    """A built Overview that reads CLIENTS, is never shown, and runs nothing."""
    monkeypatch.setattr(mod, "read_clients", lambda: CLIENTS)
    monkeypatch.setattr(mod, "read_monitors", lambda: MONITORS)
    monkeypatch.setattr(mod.thumbs, "capture", lambda client, folder: None)
    spawned = []
    monkeypatch.setattr(mod, "spawn", spawned.append)
    app = mod.Overview()
    app.build()
    app.load_apps()
    monkeypatch.setattr(app.win, "present", lambda: None)
    app.spawned = spawned
    return app


@needs_display
def test_closing_keeps_no_card_and_no_thumbnail(overview):
    """OVERVIEW-5: given an open overview with a card per window and a
    thumbnail on one, when it closes (Esc), then no card is left alive and no
    thumbnail is kept, and a number key or a pick on the next open runs the
    right command."""
    overview.show_popup()
    assert len(overview.cards) == 6
    texture = Gdk.MemoryTexture.new(1, 1, Gdk.MemoryFormat.R8G8B8A8, GLib.Bytes.new(b"\0" * 4), 4)
    overview.textures["0xa"] = texture
    refs = [weakref.ref(c) for c in overview.cards]

    overview._on_key(Gdk.KEY_Escape, 0)
    while GLib.MainContext.default().iteration(False):
        pass
    gc.collect()

    assert sum(r() is not None for r in refs) == 0
    assert overview.textures == {} and overview.cards == [] and overview.rows == []
    overview.show_popup()
    overview._on_key(Gdk.KEY_0, 0)
    overview.show_popup()
    overview.pick(overview.cards[0])
    assert overview.spawned == [mod.desk_cmd(10), mod.go_cmd("0xe")]


def test_the_overview_is_one_of_the_popups():
    """OVERVIEW-7: given popup.sh, when it is read, then `overview` is in its
    list of popups (--restart starts it hidden, --close-all, --unstick and
    doctor.sh cover it) with the D-Bus name io.local.overview."""
    sh = open(os.path.join(SCRIPTS, "popup.sh")).read()
    all_line = next(line for line in sh.splitlines() if line.startswith('all="'))
    assert "overview" in all_line.split('"')[1].split()
    assert "    overview)       echo io.local.overview ;;" in sh
    assert 'application_id="io.local.overview"' in open(os.path.join(SCRIPTS, "overview.py")).read()


def test_the_list_scrolls_to_show_the_selected_card():
    """NAV-1: given a 640 px view scrolled to 0, when the selection moves to a
    card below the view, then the list scrolls the least amount that shows the
    whole card (plus the margin); to a card above the view, up to its top; and
    for a card already in view, not at all."""
    assert scrolling.scroll_to_show(700, 850, 0, 640) == 850 - 640 + 16  # below: bottom aligned
    assert scrolling.scroll_to_show(100, 250, 400, 640) == 84  # above: top aligned
    assert scrolling.scroll_to_show(10, 160, 0, 640) is None  # in view
    assert scrolling.scroll_to_show(5, 150, 30, 640) == 0  # never above the list's top


def test_up_and_down_follow_the_lines_on_the_screen():
    """NAV-2: given desk 1 with 7 cards (a line of 5 and a wrapped line of 2)
    and desk 2 with 3 cards, when Down is pressed from the 4th card, then it
    goes to the nearest card of desk 1's second line (not to desk 2); Down again
    goes to desk 2; Up from desk 2 goes back to the wrapped line; on the first
    and the last line the selection stays."""
    x = [0, 240, 480, 720, 960]
    places = [(xi, 0) for xi in x] + [(0, 200), (240, 200)] + [(0, 420), (240, 420), (480, 420)]

    assert mod.next_line(places, 3, 1) == 6  # x 720 -> nearest on the wrapped line is x 240
    assert mod.next_line(places, 6, 1) == 8  # x 240 on desk 2
    assert mod.next_line(places, 9, -1) == 6  # x 480 -> nearest is x 240
    assert mod.next_line(places, 2, -1) == 2  # first line
    assert mod.next_line(places, 9, 1) == 9  # last line
