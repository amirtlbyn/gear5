"""The minimized-windows picker's pure logic: order, filter, number keys, and the
INV-3/INV-4 guards — never a real display, never a real window.
See config/waybar/scripts/minimized-picker.py."""

import os

import panel
import pytest
from conftest import ROOT

mod = panel.load("minimized-picker")


def client(address, title, cls, workspace):
    return {"address": address, "title": title, "class": cls, "workspace": {"name": workspace}}


class FakeWindow:
    def __init__(self):
        self.visible = True

    def set_visible(self, value):
        self.visible = value


class FakeFlow:
    def __init__(self, children):
        self.children = list(children)

    def get_first_child(self):
        return self.children[0] if self.children else None

    def remove(self, child):
        self.children.remove(child)


class FakeApp:
    """A stand-in for Picker: leave() touches self.win, self.closed_at and, through
    drop_cards, the cards, their thumbnails and the grid."""

    def __init__(self):
        self.win = FakeWindow()
        self.closed_at = 0
        self.flow = FakeFlow(["card 1", "card 2"])
        self.cards, self.items, self.windows = ["card 1", "card 2"], [{}, {}], [{}, {}]
        self.textures = {"0x1": object(), "0x2": object()}

    def drop_cards(self):
        mod.Picker.drop_cards(self)


def test_minimized_windows_are_returned_newest_hidden_first(tmp_path):
    """BATPICK-7: given clients and the order file hyprland.lua keeps (oldest to
    newest), when the picker reads the minimized windows, then they come back
    newest-hidden-first, ready to number 1..9 in that order."""
    clients = [
        client("0x1", "kitty A", "kitty", "special:minimized"),
        client("0x2", "kitty B", "kitty", "special:minimized"),
        client("0x3", "Zen", "zen", "1"),  # not minimized: left out
    ]
    order_file = tmp_path / "hypr-minimized"
    order_file.write_text("0x1\n0x2\n")  # 0x1 hidden first, 0x2 hidden last
    windows = mod.minimized_windows(clients, order_file=str(order_file))
    assert [c["address"] for c in windows] == ["0x2", "0x1"]


def test_typing_filters_by_title_and_app_and_numbers_the_first_nine_cards():
    """BATPICK-8: given the filter text typed into the picker, when the grid is
    rebuilt, then only windows whose title or app matches every typed word stay,
    in the same order, and the number keys 1-9 map onto that filtered list."""
    windows = [
        client("0x1", "kitty — build", "kitty", "special:minimized"),
        client("0x2", "kitty — chat", "kitty", "special:minimized"),
        client("0x3", "Zen Browser", "zen", "special:minimized"),
    ]
    for text, expected_addresses in (
        ("", ["0x1", "0x2", "0x3"]),  # empty filter: everything, unchanged order
        ("kitty", ["0x1", "0x2"]),  # matches the app, not the title alone
        ("chat", ["0x2"]),  # matches only the title
        ("zen browser", ["0x3"]),  # every typed word must match
        ("nope", []),  # nothing matches
    ):
        filtered = mod.filter_windows(windows, text)
        assert [c["address"] for c in filtered] == expected_addresses, text
    filtered = mod.filter_windows(windows, "kitty")
    assert mod.number_target(filtered, 1)["address"] == "0x1"
    assert mod.number_target(filtered, 2)["address"] == "0x2"
    assert mod.number_target(filtered, 3) is None  # past the filtered list
    assert mod.number_target(filtered, 10) is None  # past MAX_NUMBERED


def test_nothing_minimized_leaves_the_picker_with_no_window_to_show():
    """BATPICK-9: given clients where none sits on special:minimized, when the
    picker reads them, then there is nothing to show — the picker's empty state,
    not a text list of windows that aren't there."""
    clients = [
        client("0x1", "Zen", "zen", "1"),
        client("0x2", "kitty", "kitty", "2"),
    ]
    assert mod.minimized_windows(clients) == []


def test_the_bar_counter_the_keybind_and_the_docs_point_at_the_new_picker():
    """BATPICK-10: given the bar's minimized counter, the SUPER+SHIFT+- keybind,
    the README and docs/SCREENSHOTS.md, when they are read, then the counter and
    the keybind open minimized-picker (not the old launcher list), and both docs
    describe the Battery page and the picker."""
    modules = open(os.path.join(ROOT, "config", "waybar", "bar", "modules.jsonc")).read()
    hyprland = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    readme = open(os.path.join(ROOT, "README.md")).read()
    shots = open(os.path.join(ROOT, "docs", "SCREENSHOTS.md")).read()
    assert "popup.sh minimized-picker" in modules
    assert "popup.sh launcher --minimized" not in modules
    assert 'popup.sh minimized-picker")' in hyprland
    assert '"SHIFT + minus", exec("~/.config/waybar/scripts/popup.sh launcher --minimized")' not in hyprland
    assert "Minimized windows" in readme and "Battery" in readme
    assert "Minimized windows" in shots and "Battery" in shots


def test_still_minimized_refuses_a_window_that_is_no_longer_on_the_special_desk():
    """INV-3: given an address that used to be minimized, when the picker
    re-reads clients right before acting, then it treats the window as gone the
    moment a fresh read shows it left special:minimized, and as still there
    while a fresh read agrees."""
    moved = [client("0x1", "kitty", "kitty", "1")]
    assert mod.still_minimized("0x1", moved) is False
    still_there = [client("0x1", "kitty", "kitty", "special:minimized")]
    assert mod.still_minimized("0x1", still_there) is True
    gone = [client("0x2", "Zen", "zen", "special:minimized")]
    assert mod.still_minimized("0x1", gone) is False
    # never builds a hyprctl eval/dispatch string from anything but hyprctl's own
    # address shape, however a client list came to have it
    odd = [client('0x1"); os.exit()', "kitty", "kitty", "special:minimized")]
    assert mod.still_minimized('0x1"); os.exit()', odd) is False


def test_leave_hides_the_window_even_when_its_exit_action_raises():
    """INV-4: given an exit action (a restore, say) that raises, when leave()
    runs it, then the window is hidden — the keyboard released — before the
    error is left to propagate, so no exit path can strand the keyboard."""
    app = FakeApp()

    def boom():
        raise RuntimeError("hyprctl is gone")

    with pytest.raises(RuntimeError):
        mod.Picker.leave(app, boom)
    assert app.win.visible is False


def test_window_commands_refuse_anything_but_a_hyprctl_address():
    """INV-3: the Lua text is built only from a real address, and close goes
    through closeMinimized, which checks again inside Hyprland."""
    assert mod.close_cmd("0x1a") == ["hyprctl", "eval", 'closeMinimized("0x1a")']
    for bad in ('0x1") os.execute("x', "", None, "1a"):
        with pytest.raises(ValueError):
            mod.restore_cmd(bad)
        with pytest.raises(ValueError):
            mod.close_cmd(bad)


def test_no_thumbnails_without_a_private_runtime_dir():
    """Captures show other windows' content: with no XDG_RUNTIME_DIR there is
    no capture at all, never a shared /tmp folder."""
    assert mod.capture_thumbnail({"stableId": "18000048", "address": "0x1"}, thumb_dir=None) is None


def test_closeminimized_checks_the_window_is_still_hidden():
    """INV-3 on the Hyprland side: closeMinimized closes only a hidden window."""
    lua = open(os.path.join(ROOT, "config", "hypr", "hyprland.lua")).read()
    body = lua.split("function closeMinimized(addr)", 1)[1].split("\nend", 1)[0]
    assert "if not isMinimized(w) then return end" in body


def test_closing_the_picker_drops_its_cards_and_thumbnails():
    """PH0-4: given a picker showing two cards with thumbnails, when it closes,
    then it keeps no card, no thumbnail and no grid child while hidden."""
    app = FakeApp()
    mod.Picker.leave(app)
    assert app.win.visible is False
    assert app.textures == {} and app.cards == [] and app.flow.children == []


def test_every_selection_scrolls_the_selected_card_into_view(monkeypatch):
    """PICKNAV-1: given a picker with 12 cards, when the selection moves (the
    arrow keys, a filter and a close all go through select), then each time the
    shared scroll helper is asked to show the newly selected card of the
    picker's list, also when the index is clamped to the last card."""
    shown = []
    monkeypatch.setattr(mod.scrolling, "reveal", lambda scroll, content, card: shown.append((scroll, content, card)))

    class Card:
        def set_selected(self, on):
            self.on = on

    picker = type("P", (), {})()
    picker.cards, picker.selected, picker.scroll, picker.flow = [Card() for _ in range(12)], 0, "scroll", "flow"

    mod.Picker.select(picker, 9)
    mod.Picker.select(picker, 50)

    assert shown == [("scroll", "flow", picker.cards[9]), ("scroll", "flow", picker.cards[11])]
    assert picker.cards[11].on and not picker.cards[9].on
