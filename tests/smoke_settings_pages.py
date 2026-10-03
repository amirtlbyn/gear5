"""
Build every Settings page once, with the window hidden, and let the panels read the
system for a few seconds. Run by smoke_popups.sh on a private D-Bus session:

    GTK_A11Y=none dbus-run-session --config-file=tests/private-bus.conf -- python3 tests/smoke_settings_pages.py

Exit 0 when every panel page was built and nothing raised.
"""

import os
import subprocess
import sys
import tempfile

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "waybar", "scripts")
)
sys.argv = ["settings.py", "--hidden"]
import brightness  # noqa: E402
import power_mode  # noqa: E402
import settings  # noqa: E402
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

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
    """BATT-2: the Power & sleep page stacks the power panel only — the battery
    card moved to the Battery page and brightness to Displays. In Settings the
    power panel starts with the POWER MODE row, above WHEN I'M AWAY, with the
    active mode marked."""
    app.show_page("power")
    app.page_shown("power")
    panels = app.panels.get("power", ())
    names = [type(p).__name__ for p, _m, _pv in panels]
    problems = []
    if names != ["PowerPanel"]:
        problems.append(f"the page stacks {names}, not PowerPanel alone")
    power = next((p for p, _m, _pv in panels if type(p).__name__ == "PowerPanel"), None)
    if power is None:
        problems.append("no PowerPanel on the page")
    else:
        children = []
        child = power.root.get_first_child()
        while child is not None:
            children.append(child)
            child = child.get_next_sibling()
        away = next((i for i, c in enumerate(children)
                     if isinstance(c, Gtk.Label) and "AWAY" in (c.get_label() or "")), None)
        try:
            mode_at = children.index(power.profile_row)
        except ValueError:
            mode_at = None
        active = [k for k, b in power.profile_btns.items() if b.has_css_class("on")]
        if mode_at is None or (away is not None and mode_at > away):
            problems.append("the POWER MODE row is missing or not above WHEN I'M AWAY")
        if len(active) != 1:
            problems.append(f"{len(active)} power modes marked active, not 1")
    for what in problems:
        failed.append("power")
        print(f"FAIL power page: {what}", file=sys.stderr)
    return False


def check_power_pick():
    """BATT-2: picking a mode on the row applies it through the shared helper
    (power_mode.set_profile, the same call the quick settings card makes) and
    marks the picked mode at once."""
    panels = app.panels.get("power", ())
    power = next((p for p, _m, _pv in panels if type(p).__name__ == "PowerPanel"), None)
    if power is None or not power.profile_btns:
        failed.append("power pick")
        print("FAIL power pick: no power mode row", file=sys.stderr)
        return False
    calls = []
    real = power_mode.set_profile
    power_mode.set_profile = lambda key: calls.append(key)
    try:
        other = next(k for k in power.profile_btns if k != power.profile)
        power.profile_btns[other].emit("clicked")
    finally:
        power_mode.set_profile = real
    problems = [
        what
        for what, bad in (
            (f"the pick called {calls}, not [{other!r}]", calls != [other]),
            ("the picked mode is not marked", not power.profile_btns[other].has_css_class("on")),
        )
        if bad
    ]
    for what in problems:
        failed.append("power pick")
        print(f"FAIL power pick: {what}", file=sys.stderr)
    return False


def check_battery_page():
    """BATPICK-2: the Battery page builds the Full/Balanced/Desk presets, a
    "Stop charging at" slider (80-100), a "Start charging at" slider (40 to
    stop - 5) and a Fast/Standard charge speed dropdown, and saves a pick at once.
    BATT-3: the whole battery card sits on this page — percentage, state and the
    stat line (health, cycles, watts) next to the limits."""
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
    # BATT-3: the fields of the card itself, from the real battery
    mod = panels[0][1]
    st = mod.battery.read()
    if st is None:
        problems.append("no battery: the card fields could not be checked")
    else:
        stat = p.stat.get_label()
        for what, bad in (
            ("the percentage is not shown", p.pct.get_label() != f"{st['capacity']}%"),
            ("the state is not shown", not p.state.get_label()),
            ("the stat line is not shown", not stat),
            ("the stat line has no health",
             st["health_pct"] is not None and f"Health {st['health_pct']}%" not in stat),
            ("the stat line has no cycles",
             st["cycle_count"] is not None and f"{st['cycle_count']} cycles" not in stat),
            ("the stat line has no watts",
             st["power_watts"] is not None and f"{st['power_watts']} W" not in stat),
        ):
            if bad:
                problems.append(what)
    # and a pick is saved at once; the save and the rule are intercepted, so the
    # test never touches the real user-settings.json or the real battery
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


bright_tries = 5  # retries before "the background read never landed" fails the smoke


def check_displays_brightness():
    global bright_tries
    """BRT-1, BRT-2: the Displays page has a Brightness slider one row under
    Mirror, holding the selected screen's own value; a screen with no control
    (a disabled one) gets an insensitive slider; and moving it writes only that
    screen, through the shared brightness module. Retries while the background
    read is out, and fails when it never lands."""
    p = next((pn for pn, _m, _pv in app.panels.get("displays", ())), None)
    if p is None:
        failed.append("displays brightness")
        print("FAIL no DisplaysPanel on the displays page", file=sys.stderr)
        return False
    if not p.bright:  # brightness.read_screens has not answered yet: try again
        bright_tries -= 1
        if bright_tries <= 0:
            failed.append("displays brightness")
            print("FAIL displays brightness: the background read never landed", file=sys.stderr)
            return False
        return True
    s = p.screen(p.sel)
    sc = p.bright_screen(s) if s else None
    problems = []
    if s is None or sc is None:
        problems.append("no brightness entry for the selected screen")
    else:
        grid = p.bright_scale.get_parent().get_parent()
        mirror = grid.get_child_at(0, 4)
        bright = grid.get_child_at(0, 5)
        for what, bad in (
            ("the row above Brightness is not Mirror",
             not isinstance(mirror, Gtk.Label) or mirror.get_label() != "Mirror"),
            ("there is no Brightness row under Mirror",
             not isinstance(bright, Gtk.Label) or bright.get_label() != "Brightness"
             or grid.get_child_at(1, 5) is not p.bright_scale.get_parent()),
            ("the slider does not hold the selected screen's value",
             int(p.bright_scale.get_value()) != sc["value"]),
            ("the slider is not sensitive on a screen with a control",
             not p.bright_scale.get_sensitive()),
        ):
            if bad:
                problems.append(what)
        was = p.sel
        # another screen with a control: the slider follows its value
        other = next((o.name for o in p.screens
                      if o.name != p.sel and o.enabled and p.bright_screen(o)), None)
        if other:
            p.select(other)
            sc2 = p.bright_screen(p.screen(p.sel))
            if sc2 is None or int(p.bright_scale.get_value()) != sc2["value"]:
                problems.append("selecting another screen did not move the slider to its value")
        # a screen with no control (off): the slider turns insensitive
        off = next((o.name for o in p.screens if o.name != was and not o.enabled), None)
        if off:
            p.select(off)
            if p.bright_scale.get_sensitive():
                problems.append("a screen with no control has a sensitive slider")
        p.select(was)
    # a move writes this screen only, through the shared module
    if s is not None and sc is not None:
        low = p.bright_scale.get_adjustment().get_lower()
        target = max(low, sc["value"] - 7)
        if target == sc["value"]:  # already at the bottom: move up instead
            target = min(100, sc["value"] + 7)
        if target != sc["value"]:
            calls = []
            real = brightness.set
            brightness.set = lambda sc_, value: calls.append((sc_["key"], value))
            try:
                p.bright_scale.set_value(target)
            finally:
                brightness.set = real
            if calls != [(sc["key"], target)]:
                problems.append(f"moving the slider called {calls}, not [{(sc['key'], target)}]")
    for what in problems:
        failed.append("displays brightness")
        print(f"FAIL displays brightness: {what}", file=sys.stderr)
    return False


def sticker_rows(box):
    """{title: row} of the Stickers page: a row is a Box whose first child holds the title label."""
    rows, child = {}, box.get_first_child()
    while child is not None:
        first = child.get_first_child() if isinstance(child, Gtk.Box) else None
        title = first.get_first_child() if isinstance(first, Gtk.Box) else None
        if isinstance(title, Gtk.Label):
            rows[title.get_label()] = child
        child = child.get_next_sibling()
    return rows


def row_widgets(row):
    widgets, child = [], row.get_first_child().get_next_sibling()
    while child is not None:
        widgets.append(child)
        child = child.get_next_sibling()
    return widgets


def with_scratch_settings(tmp):
    """Point the Stickers page at a scratch config: user-settings.json in tmp, a custom theme
    "nika" in the list, the background work run in place. Returns the undo function."""
    real = dict(load=settings.store.load, bg=settings.in_background, avail=settings.palette.available)
    os.makedirs(os.path.join(tmp, "hypr"))
    settings.store.load = lambda *_a: real["load"](tmp)
    settings.palette.available = lambda *_a: [*real["avail"](), ("nika", "Nika", "")]
    settings.in_background = lambda work, done: done(work())

    def undo():
        settings.store.load, settings.in_background = real["load"], real["bg"]
        settings.palette.available = real["avail"]

    return undo


def check_stickers_page():
    """GIFT-9 (session 1): given a custom theme, when the Stickers page is built, then it has
    the two switches (on by default) and a row for the custom theme with GIF... and Remove,
    and the Remove button is off while the theme has no GIF."""
    with tempfile.TemporaryDirectory() as tmp:
        undo = with_scratch_settings(tmp)
        try:
            rows = sticker_rows(app.stickers_page())
            switches = [
                row_widgets(rows[t])[-1].get_active()
                for t in ("GIF on the bar", "GIF on theme switch")
            ]
            choose, remove = row_widgets(rows["Nika"])
        finally:
            undo()
    problems = [
        what
        for what, bad in (
            ("a switch is not on by default", switches != [True, True]),
            ("the buttons are not GIF... and Remove", (choose.get_label(), remove.get_label()) != ("GIF…", "Remove")),
            ("Remove is on with no GIF", remove.get_sensitive()),
        )
        if bad
    ]
    for what in problems:
        failed.append("stickers page")
        print("FAIL stickers page: " + what, file=sys.stderr)
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
GLib.timeout_add(1450, check_power_pick)
GLib.timeout_add(1000, check_displays_brightness)
GLib.timeout_add(1550, check_stickers_page)
GLib.timeout_add(1600, visit_fonts)
GLib.timeout_add(1500, visit_editor)
GLib.timeout_add(1500, lambda: open_page("input"))  # the old name of Keyboard & touchpad
GLib.timeout_add(4000, lambda: expect("keyboard") or open_page("wifi"))
GLib.timeout_add(6500, lambda: expect("wifi"))
GLib.timeout_add(7000, finish)
app.run(sys.argv)
sys.exit(1 if failed else 0)
