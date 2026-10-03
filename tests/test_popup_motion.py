"""The popups' entry motion (roadmap 4.1, spec MOTION): bar popups slide down and
fade in, centered popups scale in, the picker's cards scale in on open, and
nothing moves when Settings turns animations off. The tests build real widgets
and never show a window; without a display they are skipped."""

import ast
import importlib
import os
import re

import gi
import panel
import pytest
import settings_store
from conftest import SCRIPTS

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gtk

pb = importlib.import_module("popup_backdrop")  # after the versions above

needs_display = pytest.mark.skipif(not Gtk.init_check(), reason="needs a display")


def popup_tree(valign=Gtk.Align.START, margin_top=64):
    """A popup window's content: an overlay with the backdrop and the .popup box,
    which holds a nested .popup panel (as control-center's does)."""
    box = Gtk.Box(valign=valign, margin_top=margin_top)
    box.add_css_class("popup")
    nested = Gtk.Box()
    nested.add_css_class("popup")
    box.append(nested)
    backdrop = Gtk.Box()
    backdrop.add_css_class("backdrop")
    overlay = Gtk.Overlay()
    overlay.set_child(backdrop)
    overlay.add_overlay(box)
    return overlay, box, nested


class FakeWindow:
    def __init__(self, child):
        self.child = child

    def get_visible(self):
        return True

    def get_child(self):
        return self.child


class FakeCatchers:
    def show(self):
        pass


def motion_classes(widget):
    return [c for c in pb.MOTION_CLASSES if widget.has_css_class(c)]


@needs_display
def test_each_open_takes_the_other_animation():
    """MOTION-1: given a popup window, when it becomes visible, then its
    outermost .popup box gets an entry class whose animation differs from the
    previous open's, and the nested .popup panel gets none."""
    overlay, box, nested = popup_tree()
    win = FakeWindow(overlay)
    seen = []
    for _ in range(3):
        pb.Catchers.on_visible(FakeCatchers(), win, None)
        assert len(motion_classes(box)) == 1
        seen.append(motion_classes(box)[0])
    assert seen[0] != seen[1] and seen[1] != seen[2]
    assert motion_classes(nested) == []
    names = {
        m.group(1)
        for c in seen
        for m in [re.search(rf"\.popup\.{c} \{{ animation: (\S+)", pb.MOTION_CSS)]
    }
    assert len(names) == 2


@needs_display
def test_bar_popups_slide_and_centered_popups_scale():
    """MOTION-2: given a box aligned to the top within the bar's reach, then the
    entry is a fade and an 8 px slide down; given a centered box, or one aligned
    to the top far below the bar (the launcher), then it is a fade and a scale
    from 97 %; both take 120 ms."""
    assert pb.motion_kind(popup_tree(Gtk.Align.START, 64)[1]) == "slide"
    assert pb.motion_kind(popup_tree(Gtk.Align.START, 72)[1]) == "slide"
    assert pb.motion_kind(popup_tree(Gtk.Align.START, 160)[1]) == "scale"
    assert pb.motion_kind(popup_tree(Gtk.Align.CENTER, 0)[1]) == "scale"
    for n in "ab":
        assert re.search(
            rf"popup-slide-{n} \{{ from \{{ opacity: 0; transform: translateY\(-8px\);",
            pb.MOTION_CSS,
        )
        assert re.search(
            rf"popup-scale-{n} \{{ from \{{ opacity: 0; transform: scale\(0\.97\);",
            pb.MOTION_CSS,
        )
    assert pb.MOTION_CSS.count("120ms ease-out") == 4


class FakePicker:
    def __init__(self):
        self.flow = Gtk.FlowBox()
        self.opening_timer = 0


@needs_display
def test_picker_cards_scale_in_only_on_open(monkeypatch):
    """MOTION-3: given the picker opens, then its grid is "opening" (the cards
    scale in from 94 % in 160 ms) and stops being so after 300 ms, so cards drawn
    while typing do not animate; show_popup marks the grid before it draws."""
    mod = panel.load("minimized-picker")
    timers = []
    monkeypatch.setattr(
        mod.GLib, "timeout_add", lambda ms, fn: timers.append((ms, fn)) or len(timers)
    )
    monkeypatch.setattr(mod.GLib, "source_remove", lambda _id: None)
    picker = FakePicker()
    mod.Picker.mark_opening(picker)
    assert picker.flow.has_css_class("opening")
    ms, done = timers[-1]
    assert ms == 300
    done()
    assert not picker.flow.has_css_class("opening")
    assert re.search(
        r"@keyframes card-in \{ from \{ opacity: 0; transform: scale\(0\.94\);", mod.CSS
    )
    assert ".opening .card { animation: card-in 160ms ease-out; }" in mod.CSS

    with open(os.path.join(SCRIPTS, "minimized-picker.py"), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    show = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "show_popup"
    )
    calls = [
        n.func.attr
        for n in ast.walk(show)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]
    assert calls.index("mark_opening") < calls.index("render")


@needs_display
def test_no_motion_when_animations_are_off(monkeypatch):
    """MOTION-4: given Settings > Animations is off, when a popup attaches, then
    GTK's gtk-enable-animations is off; given it is on, then it is on."""
    s = Gtk.Settings.get_default()
    before = s.props.gtk_enable_animations
    try:
        for on in (False, True):
            monkeypatch.setattr(
                settings_store,
                "load",
                lambda on=on: dict(settings_store.DEFAULTS, animations=on),
            )
            pb.motion_setting()
            assert s.props.gtk_enable_animations is on
    finally:
        s.props.gtk_enable_animations = before
