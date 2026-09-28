"""
Build every Settings page once, with the window hidden, and let the panels read the
system for a few seconds. Run by smoke_popups.sh on a private D-Bus session:

    GTK_A11Y=none dbus-run-session -- python3 tests/smoke_settings_pages.py

Exit 0 when every panel page was built and nothing raised.
"""

import os
import subprocess
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts")
)
sys.argv = ["settings.py", "--hidden"]
import settings  # noqa: E402
from gi.repository import Gdk, GLib  # noqa: E402

calls = []  # (page, method) of every Settings.panel_call, from the first one
_panel_call = settings.Settings.panel_call


def recording_panel_call(self, key, method, *args):
    calls.append((key, method))
    return _panel_call(self, key, method, *args)


settings.Settings.panel_call = recording_panel_call
app = settings.Settings()
failed = []
sys.excepthook = lambda *exc: (failed.append(exc), sys.__excepthook__(*exc))


def check_prefetch():
    """SETFIX-3: before any page is opened, Settings has built every panel page in
    the background and let its panels read the system once (on_show while hidden)."""
    for key in settings.PANELS:
        if key not in app.panels or (key, "on_show") not in calls:
            failed.append("prefetch " + key)
            print(f"FAIL panel page {key} was not prefetched", file=sys.stderr)
    return False


def check_panel_calls():
    """SETFIX-1: a panel page's on_show, on_hide, on_key and on_escape reach every
    panel on it (Displays reads its screens, Wi-Fi closes its open row on Esc)."""
    for key in settings.PANELS:
        app.show_page(key)
        got = []
        for p, _mod, _provider in app.panels[key]:
            for method in ("on_show", "on_hide", "on_key", "on_escape"):
                setattr(p, method, lambda *_a, p=p, m=method: got.append((p, m)))
        app.page_shown(key)
        app.panel_hidden(key)
        app.panel_call(key, "on_key", Gdk.KEY_Return)
        app.panel_call(key, "on_escape")
        for p, _mod, _provider in app.panels[key]:
            for method in ("on_show", "on_hide", "on_key", "on_escape"):
                if (p, method) not in got:
                    failed.append(f"{key} {method}")
                    print(f"FAIL {key}: {type(p).__name__}.{method} was not called", file=sys.stderr)
                delattr(p, method)
    return False


def check_theme_pick():
    """SETFIX-2: picking a theme keeps the Theme page's ScrolledWindow, its content
    and its scroll, and moves the "in use" badge and the current style to the
    picked card. theme.py is not run: the switch itself is theme.py's job."""
    app.show_page("theme")
    sw = app.stack.get_child_by_name("theme")
    content = sw.get_child()
    adj = sw.get_vadjustment()
    adj.set_value(min(300, max(0, adj.get_upper() - adj.get_page_size())))
    pos = adj.get_value()
    old = settings.palette.current()
    new = next(t for t in app.theme_cards if t != old)
    real_bg, real_current = settings.in_background, settings.palette.current

    def switched(_work, done):  # as if theme.py applied it
        settings.palette.current = lambda: new
        done(None)

    settings.in_background = switched
    try:
        app.pick_theme(new)
    finally:
        settings.in_background, settings.palette.current = real_bg, real_current
        app.busy = False
    card, top = app.theme_cards[new]
    problems = [
        what
        for what, bad in (
            ("the ScrolledWindow was replaced", app.stack.get_child_by_name("theme") is not sw),
            ("the page was rebuilt", sw.get_child() is not content),
            (f"the scroll moved from {pos:.0f} to {adj.get_value():.0f}", abs(adj.get_value() - pos) > 1),
            ("the picked card is not current", not card.has_css_class("current")),
            ("the badge is not on the picked card", app.theme_badge.get_parent() is not top),
            ("the old card is still current", app.theme_cards[old][0].has_css_class("current")),
        )
        if bad
    ]
    for what in problems:
        failed.append("theme pick")
        print("FAIL theme pick: " + what, file=sys.stderr)
    app.mark_theme(old)
    return False


def visit():
    for key, _icon, _name in settings.PAGES:
        app.show_page(key)
        app.page_shown(key)  # as if the window were open
        app.panel_hidden(key)
        if key in settings.PANELS and key not in app.panels:
            failed.append(key)
            print("FAIL page " + key, file=sys.stderr)
    app.apply_css()  # a theme switch recolors every panel
    return False


def visit_power():
    """G5-3, G5-4, G5-6: the Power & sleep page stacks three panels — battery and
    power mode, one brightness slider per screen, and the power panel with the
    Lock / Sleep / Reboot / Power off actions — and the first two read the real
    system in the background once shown."""
    app.show_page("power")
    app.page_shown("power")
    n = len(app.panels.get("power", ()))
    if n != 3:
        failed.append("power")
        print(f"FAIL power page has {n} panels, not 3", file=sys.stderr)
    return False


def check_battery_page():
    """BATPICK-2: the Battery page builds the Full/Balanced/Desk presets, a
    "Stop charging at" slider (80-100), a "Start charging at" slider (40 to
    stop - 5) and a Fast/Standard charge speed dropdown, and saves a pick at once."""
    app.show_page("battery")
    app.page_shown("battery")
    panels = app.panels.get("battery", ())
    if len(panels) != 1:
        failed.append("battery")
        print(f"FAIL battery page has {len(panels)} panels, not 1", file=sys.stderr)
        return False
    p = panels[0][0]
    speeds = [p.speed_drop.get_model().get_string(i) for i in range(p.speed_drop.get_model().get_n_items())]
    problems = [
        what
        for what, bad in (
            ("presets are not Full/Balanced/Desk", set(p.preset_btns) != {"full", "balanced", "desk"}),
            (
                "the stop slider's range is not 80-100",
                (p.stop_pct_scale.get_adjustment().get_lower(), p.stop_pct_scale.get_adjustment().get_upper())
                != (80, 100),
            ),
            (
                "the start slider's range is not 40..stop-5",
                (
                    p.start_pct_scale.get_adjustment().get_lower(),
                    p.start_pct_scale.get_adjustment().get_upper(),
                )
                != (40, p.stop_pct - 5),
            ),
            ("the speed dropdown is not Fast/Standard", speeds != ["Fast", "Standard"]),
        )
        if bad
    ]
    # and a pick is saved at once; the save and the rule are intercepted, so the
    # test never touches the real user-settings.json or the real battery
    mod = panels[0][1]
    saved = []
    real_save, real_tick = mod.store.save, mod.battery.tick
    mod.store.save = lambda s, *_a, **_k: saved.append(s)
    mod.battery.tick = lambda *_a, **_k: None
    try:
        p.pick_preset("balanced")
    finally:
        mod.store.save, mod.battery.tick = real_save, real_tick
    if not saved or (saved[-1]["battery_stop"], saved[-1]["battery_start"]) != (90, 80):
        problems.append("picking Balanced did not save stop 90 / start 80")
    for what in problems:
        failed.append("battery")
        print("FAIL battery page: " + what, file=sys.stderr)
    return False


def visit_editor():
    """The theme editor: a new theme, and editing an existing one, builds every color
    picker and the Advanced expander (GEAR-9, GEAR-10, GEAR-13), then one color change
    runs the live-preview redraw (GEAR-11)."""
    app.open_editor(None)
    app.open_editor(settings.palette.DEFAULT)
    picked = Gdk.RGBA()
    picked.parse("#334455")
    app.editor_choosers["bg"].props.rgba = picked
    app.show_page("theme")
    return False


def visit_fonts():
    """FONT-1: the Fonts page builds — its two family choosers, the live sample
    and Apply — from the machine's real font map."""
    app.show_page("fonts")
    app.page_shown("fonts")
    return False


def open_page(name):
    """`settings.py NAME --hidden`, as SUPER+I or a terminal would, to the running Settings."""
    subprocess.Popen([sys.executable, os.path.join(settings.SCRIPTS, "settings.py"), name, "--hidden"])
    return False


def expect(page):
    if app.page != page:
        failed.append(page)
        print(f"FAIL command line opened {app.page}, not {page}", file=sys.stderr)
    return False


def finish():
    app.quit()
    return False


GLib.timeout_add(500, check_prefetch)
GLib.timeout_add(500, visit)
GLib.timeout_add(900, check_panel_calls)
GLib.timeout_add(1000, check_theme_pick)
GLib.timeout_add(1350, visit_power)
GLib.timeout_add(1400, check_battery_page)
GLib.timeout_add(1450, visit_fonts)
GLib.timeout_add(1500, visit_editor)
GLib.timeout_add(1500, lambda: open_page("input"))  # the old name of Keyboard & touchpad
GLib.timeout_add(4000, lambda: expect("keyboard") or open_page("wifi"))
GLib.timeout_add(6500, lambda: expect("wifi"))
GLib.timeout_add(7000, finish)
app.run(sys.argv)
sys.exit(1 if failed else 0)
