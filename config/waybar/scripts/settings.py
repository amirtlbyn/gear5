#!/usr/bin/env python3
"""
Settings (SUPER+I, or the button in the control center), in the theme's colors.

  settings.py [PAGE]      open on that page: theme, wallpaper, displays, wifi, bluetooth,
                          sound, power, notifications, keyboard, look
  settings.py theme-new           open the theme editor for a new theme
  settings.py theme-edit-ID       open the theme editor for a custom theme

- Theme: pick a Straw Hat (or Summer night); everything switches at once. A "New
  theme" card and, on a made theme, Edit, Rename and Delete open the editor below.
- Wallpaper: one image for every theme, copied into ~/.config/hypr/wallpapers/.
- Displays, Wi-Fi, Bluetooth, Sound, Power & sleep: the bar popups' own panels
  (see panel.py), so every setting is here and nothing opens another app.
- Notifications: Do Not Disturb and Clear all (swaync).
- Keyboard & touchpad, Look & behavior: layouts, touchpad, gaps, animations.
  Kept in ~/.config/hypr/user-settings.json (see settings_store.py).

A normal window, not a popup: the file chooser has to be able to open over it.
"""
import math
import os
import shutil
import subprocess
import sys
import threading
import traceback

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("PangoCairo", "1.0")
try:
    gi.require_version("Gtk4LayerShell", "1.0")  # popup_backdrop imports it
except ValueError:
    pass
import palette  # noqa: E402
import panel  # noqa: E402
import popup_backdrop  # noqa: E402
import settings_store as store  # noqa: E402
import theme_maker  # noqa: E402
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo  # noqa: E402

HYPRPICKER = shutil.which("hyprpicker")  # the eyedropper button hides without it

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
THEME_PY = os.path.join(SCRIPTS, "theme.py")
PAGES = [
    ("theme", "\U000f03d8", "Theme"),
    ("wallpaper", "\U000f02e9", "Wallpaper"),
    ("displays", "\U000f0379", "Displays"),
    ("wifi", "\U000f05a9", "Wi-Fi"),
    ("bluetooth", "\U000f00af", "Bluetooth"),
    ("sound", "\U000f057e", "Sound"),
    ("power", "\U000f0425", "Power & sleep"),
    ("notifications", "\U000f009a", "Notifications"),
    ("keyboard", "\U000f030c", "Keyboard & touchpad"),
    ("look", "\U000f0568", "Look & behavior"),
]
SECTIONS = {"theme": "APPEARANCE", "displays": "SYSTEM", "keyboard": "INPUT & DESKTOP"}  # heading before
OLD_PAGES = {"input": "keyboard"}  # page names of earlier versions
PANELS = {  # page -> (popup, panel class): the bar popups' own panels, see panel.py
    "displays": ("displays", "DisplaysPanel"),
    "wifi": ("wifi-menu", "WifiPanel"),
    "bluetooth": ("control-center", "BluetoothPanel"),
    "sound": ("volume-popup", "VolumePanel"),
    "power": ("power-popup", "PowerPanel"),
}
IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp")

WINDOW_CSS = """
window.settings { background: @bg_dim; color: @fg; }
window.settings * { font-family: "JetBrainsMono Nerd Font", "Vazirmatn", sans-serif; }
.side { background: @bg0; padding: 16px 10px; border-right: 1px solid alpha(@fg, 0.06); }
.side .app-title { font-size: 18px; font-weight: 800; margin: 2px 10px 14px 10px; }
.side button { background: transparent; color: @fg; border: none; box-shadow: none; border-radius: 12px;
               padding: 7px 12px; font-weight: bold; }
.side .side-section { color: @grey; font-size: 10px; font-weight: bold; letter-spacing: 2px;
                      margin: 10px 12px 2px 12px; }
.side button:hover { background: @bg1; }
.side button.active { background: @green; color: @on_accent; }
.panel-page { padding: 22px 26px; }
.panel-error { color: @red; }
"""
# Settings' own pages (under .own), so they never restyle the panels
PAGE_CSS = """
.page { padding: 22px 26px; }
.page-title { font-size: 22px; font-weight: 800; }
.page-sub { color: @grey; font-size: 12.5px; margin-bottom: 16px; }
.section { color: @grey; font-size: 11px; font-weight: bold; letter-spacing: 2px; margin: 18px 2px 8px 2px; }
button.card { background: @bg0; color: @fg; border: none; box-shadow: none; border-radius: 16px;
              border-bottom: 4px solid @edge_deep; padding: 10px; }
button.card:hover { background: @bg1; }
button.card.current { box-shadow: inset 0 0 0 2px @green; }
.card .name { font-weight: 800; font-size: 14px; }
.card .char { color: @grey; font-size: 11px; }
.card .badge { color: @green; font-size: 11px; font-weight: bold; }
.row { background: @bg0; border-radius: 14px; border-bottom: 3px solid @edge_deep; padding: 10px 14px; }
.row .title { font-weight: bold; }
.row .desc { color: @grey; font-size: 11.5px; }
.row .error, .page .error { color: @red; font-size: 11.5px; }
.thumb { border-radius: 10px; }
.plain { border-radius: 10px; color: @grey; font-size: 10px; }
button.act, menubutton.act { background: @bg2; color: @fg; border: none; box-shadow: none;
             border-radius: 12px; border-bottom: 3px solid @edge_deep; padding: 6px 14px; font-weight: bold; }
button.act:hover, menubutton.act:hover { background: @bg3; }
button.act.primary, menubutton.act.primary { background: @green; color: @on_accent;
             border-bottom-color: @green_edge; }
button.act:disabled, menubutton.act:disabled { opacity: 0.4; }
button.tile { background: @bg0; color: @fg; border: none; box-shadow: none; border-radius: 16px;
              border-bottom: 4px solid @edge_deep; padding: 14px; }
button.tile:hover { background: @bg1; }
.tile .icon { font-size: 26px; color: @green; }
.tile .name { font-weight: 800; }
.tile .desc { color: @grey; font-size: 11px; }
entry { background: @bg2; color: @fg; border: none; border-radius: 10px; min-height: 32px; }
switch { background: @bg3; border: none; }
switch:checked { background: @green; }
switch slider { background: @fg; border: none; box-shadow: none; }
dropdown > button { background: @bg2; color: @fg; border: none; border-radius: 10px; box-shadow: none; }
popover > contents { background: @bg1; color: @fg; border-radius: 12px; }
scrollbar { background: transparent; }
"""


def label(text="", css=None, **kw):
    lbl = Gtk.Label(label=text, **kw)
    for c in (css or "").split():
        lbl.add_css_class(c)
    return lbl


def spawn(argv):
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def in_background(work, done=None):
    """Run work() off the UI thread; done(result) runs on it after (result is the
    exception if work() failed)."""

    def target():
        try:
            result = work()
        except Exception as e:  # noqa: BLE001 - handed to done(), never lost
            result = e
        if done:
            GLib.idle_add(lambda: (done(result), False)[1])

    threading.Thread(target=target, daemon=True).start()


def swaync(*args):
    """swaync-client's answer, or "" when notifications aren't running."""
    try:
        return subprocess.run(["swaync-client", *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def swatch(colors, names=("bg0", "fg", "green", "blue", "red", "yellow")):
    """A strip of a theme's main colors."""
    area = Gtk.DrawingArea(content_height=34, hexpand=True)

    def draw(_a, cr, w, h):
        step = w / len(names)
        for i, n in enumerate(names):
            rgba = Gdk.RGBA()
            rgba.parse(colors.get(n, "#000000"))
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
            cr.rectangle(i * step, 0, step + 1, h)
            cr.fill()

    area.set_draw_func(draw)
    area.set_overflow(Gtk.Overflow.HIDDEN)
    area.add_css_class("thumb")
    return area


def color_area(hex_color):
    """A small square of one color, for a color-picker button. Set area.color and
    call area.queue_draw() to show a new pick."""
    area = Gtk.DrawingArea(content_width=30, content_height=30)
    area.color = hex_color
    area.add_css_class("thumb")

    def draw(_a, cr, w, h):
        rgba = Gdk.RGBA()
        rgba.parse(area.color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        cr.rectangle(0, 0, w, h)
        cr.fill()

    area.set_draw_func(draw)
    return area


def rgba_to_hex(rgba):
    return "#" + "".join(f"{round(c * 255):02x}" for c in (rgba.red, rgba.green, rgba.blue))


def color_button(hex_color, on_pick):
    """A button with a color swatch; its popover is GTK's own color chooser (a plane,
    a hue slider and a hex field), plus an eyedropper that runs hyprpicker, when it is
    installed. on_pick(hex) runs on every change, live, while the popover is open."""
    area = color_area(hex_color)
    button = Gtk.MenuButton(child=area)
    button.add_css_class("act")
    popover = Gtk.Popover()
    box = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL,
        spacing=8,
        margin_top=10,
        margin_bottom=10,
        margin_start=10,
        margin_end=10,
    )
    chooser = Gtk.ColorChooserWidget(show_editor=True, use_alpha=False)
    rgba = Gdk.RGBA()
    rgba.parse(hex_color)
    chooser.props.rgba = rgba

    def changed(c, _pspec):
        value = rgba_to_hex(c.props.rgba)
        area.color = value
        area.queue_draw()
        on_pick(value)

    chooser.connect("notify::rgba", changed)
    box.append(chooser)
    if HYPRPICKER:
        pick = Gtk.Button(label="Pick from screen")
        pick.add_css_class("act")

        def eyedrop(_b):
            def work():
                return subprocess.run(
                    [HYPRPICKER, "-f", "hex"], capture_output=True, text=True, timeout=30
                ).stdout.strip()

            def done(result):
                if isinstance(result, str) and result.startswith("#") and len(result) == 7:
                    picked = Gdk.RGBA()
                    picked.parse(result)
                    chooser.props.rgba = picked

            in_background(work, done)

        pick.connect("clicked", eyedrop)
        box.append(pick)
    popover.set_child(box)
    button.set_popover(popover)
    return button, chooser


def theme_preview(colors):
    """A bar strip, a popup card with text, dim text and an accent chip, and a button,
    drawn in colors. Set area.colors and call area.queue_draw() to redraw it."""
    area = Gtk.DrawingArea(content_height=170, hexpand=True)
    area.colors = colors

    def fill(cr, x, y, w, h, hex_color, radius=0):
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        if radius:
            cr.new_sub_path()
            cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
            cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
            cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
            cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
            cr.close_path()
        else:
            cr.rectangle(x, y, w, h)
        cr.fill()

    def text(cr, x, y, s, hex_color, bold=False):
        rgba = Gdk.RGBA()
        rgba.parse(hex_color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
        layout = PangoCairo.create_layout(cr)
        layout.set_text(s, -1)
        layout.set_font_description(
            Pango.FontDescription.from_string("JetBrainsMono Nerd Font" + (" Bold" if bold else "") + " 11")
        )
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

    def draw(_a, cr, w, _h):
        c = area.colors
        fill(cr, 0, 0, w, 28, c["bg0"])
        text(cr, 10, 6, "12:30", c["fg"], bold=True)
        fill(cr, w - 66, 4, 56, 20, c["green"], radius=6)
        text(cr, w - 58, 6, "Bar", c["on_accent"])
        fill(cr, 0, 38, w, 84, c["bg1"], radius=12)
        text(cr, 16, 50, "Popup text", c["fg"], bold=True)
        text(cr, 16, 72, "Dim text", c["grey"])
        fill(cr, 16, 92, 84, 22, c["blue"], radius=11)
        text(cr, 26, 96, "Chip", c["on_accent"])
        fill(cr, 0, 134, 120, 30, c["green"], radius=10)
        text(cr, 32, 141, "Button", c["on_accent"], bold=True)

    area.set_draw_func(draw)
    return area


class Settings(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.local.settings", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.win = None
        self.provider = None
        self.page = "theme"
        self.busy = False  # a theme switch, wallpaper copy or theme save is running
        self.panels = {}  # page -> (panel, its module, its CSS provider), built when first shown
        self.theme = None  # the theme the window is drawn in

    # ----- lifecycle -----------------------------------------------------------
    def do_command_line(self, cmd):
        args = cmd.get_arguments()[1:]
        page = next((OLD_PAGES.get(a, a) for a in args if a in OLD_PAGES or a in {p for p, _i, _n in PAGES}), None)
        # theme-new and theme-edit-<id>: the editor, not a sidebar page
        editor = next((a for a in args if a == "theme-new" or a.startswith("theme-edit-")), None)
        if self.win is None:
            self.hold()
            self.build()
        was_shown = self.win.get_visible()
        if editor:
            self.open_editor(None if editor == "theme-new" else editor[len("theme-edit-") :])
        elif page:
            self.show_page(page)
        if "--hidden" not in args:  # --hidden: start in the background (tests)
            if self.theme != palette.current():  # switched from the bar or a terminal
                self.apply_css()
                self.rebuild("theme")
                self.rebuild("wallpaper")
            self.win.present()
            if not was_shown:  # a shown window: show_page already did it
                self.page_shown(self.page)
        return 0

    def do_shutdown(self):
        for p, _mod, _provider in self.panels.values():
            if hasattr(p, "stop"):  # e.g. Sound's pactl watcher, a Bluetooth scan
                p.stop()
        Gtk.Application.do_shutdown(self)

    def apply_css(self):
        if self.provider is None:
            self.provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        self.theme = palette.current()
        colors = palette.load(self.theme)
        self.provider.load_from_string(
            "".join(f"@define-color {k} {v};\n" for k, v in colors.items())
            + WINDOW_CSS
            + panel.scope(PAGE_CSS, "own")
        )
        for key, (_panel, mod, provider) in self.panels.items():
            mod.P = palette.load(self.theme, **mod.ALIASES)  # colors it draws with itself
            provider.load_from_string(panel.scoped_css(mod.STYLE, mod.P, "panel-" + key))

    def build(self):
        popup_backdrop.smooth_text()
        self.apply_css()
        win = Gtk.ApplicationWindow(application=self, title="Settings", default_width=860, default_height=640)
        win.add_css_class("settings")
        win.connect("close-request", self.on_close)
        self.win = win

        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        side.add_css_class("side")
        side.set_size_request(210, -1)
        side.append(label("\U000f0493  Settings", "app-title", xalign=0))
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hexpand=True, vexpand=True)
        self.side_btns = {}
        for key, icon, name in PAGES:
            if key in SECTIONS:
                side.append(label(SECTIONS[key], "side-section", xalign=0))
            b = Gtk.Button(label=f"{icon}   {name}")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda _b, k=key: self.show_page(k))
            side.append(b)
            self.side_btns[key] = b
        self.pages = dict(
            theme=self.theme_page,
            wallpaper=self.wallpaper_page,
            notifications=self.notifications_page,
            keyboard=self.keyboard_page,
            look=self.look_page,
        )
        for key, _icon, _name in PAGES:
            # a panel page is built the first time it is shown
            self.stack.add_named(Gtk.Box() if key in PANELS else self.scrolled(self.pages[key]()), key)

        body = Gtk.Box()
        body.append(side)
        body.append(self.stack)
        win.set_child(body)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self.on_key)
        win.add_controller(keys)
        self.show_page(self.page)

    def scrolled(self, child):
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrap.add_css_class("own")
        wrap.append(child)
        sw.set_child(wrap)
        return sw

    def rebuild(self, key):
        """Draw a page again (after a theme or wallpaper change)."""
        old = self.stack.get_child_by_name(key)
        self.stack.remove(old)
        self.stack.add_named(self.scrolled(self.pages[key]()), key)
        if self.page == key:
            self.stack.set_visible_child_name(key)

    def show_page(self, key):
        if key != self.page:
            self.panel_hidden(self.page)
        self.page = key
        if key in PANELS and key not in self.panels:
            self.build_panel(key)
        self.stack.set_visible_child_name(key)
        for k, b in self.side_btns.items():
            (b.add_css_class if k == key else b.remove_css_class)("active")
        if self.win.get_visible():
            self.page_shown(key)

    def on_close(self, win):
        self.panel_hidden(self.page)
        win.set_visible(False)
        return True

    # ----- panels (the bar popups' own panels, see panel.py) ---------------------------
    def build_panel(self, key):
        name, cls = PANELS[key]
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        page.add_css_class("panel-page")
        page.add_css_class("panel-" + key)
        try:
            mod = panel.load(name)
            p = getattr(mod, cls)(PageHost(self, key))
        except Exception as e:  # noqa: BLE001 - one broken panel must not take Settings down
            traceback.print_exc()
            page.append(label(f"This page couldn't start: {e}", "panel-error", xalign=0, wrap=True))
        else:
            provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
            self.panels[key] = (p, mod, provider)
            self.apply_css()
            page.append(p.root)
        self.stack.remove(self.stack.get_child_by_name(key))
        sw = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        sw.set_child(page)
        self.stack.add_named(sw, key)

    def page_shown(self, key):
        """The page just came into view: show what is true now."""
        if key in self.panels:
            self.panel_call(key, "on_show")
        elif key == "notifications":
            self.read_notifications()

    def panel_hidden(self, key):
        if key in self.panels:
            self.panel_call(key, "on_hide")

    def panel_call(self, key, method, *args):
        """A panel's method; an error in it is printed, and Settings keeps running."""
        try:
            return getattr(self.panels[key][0], method)(*args)
        except Exception:  # noqa: BLE001 - one broken panel must not take Settings down
            traceback.print_exc()
            return None

    def on_key(self, _ctl, keyval, _code, state):
        p = self.panels.get(self.page, (None,))[0]
        if keyval == Gdk.KEY_Escape and hasattr(p, "on_escape") and self.panel_call(self.page, "on_escape"):
            return True  # e.g. Wi-Fi closes its open row first
        if keyval == Gdk.KEY_Escape or (state & Gdk.ModifierType.CONTROL_MASK and keyval == Gdk.KEY_w):
            self.win.close()
            return True
        if hasattr(p, "on_key") and keyval not in (Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):  # Tab moves the focus
            return bool(self.panel_call(self.page, "on_key", keyval))  # e.g. Enter applies on Displays
        return False

    def page_box(self, title, sub):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.add_css_class("page")
        box.append(label(title, "page-title", xalign=0))
        box.append(label(sub, "page-sub", xalign=0, wrap=True))
        return box

    # ----- theme -------------------------------------------------------------------
    def theme_page(self):
        box = self.page_box(
            "Theme",
            "Pick a character. The bar, popups, notifications, window borders, "
            "lock screen and wallpaper all switch together.",
        )
        current = palette.current()
        flow = Gtk.FlowBox(
            selection_mode=Gtk.SelectionMode.NONE,
            homogeneous=True,
            max_children_per_line=3,
            min_children_per_line=2,
            column_spacing=12,
            row_spacing=12,
        )
        new_card = Gtk.Button(can_focus=True)
        new_card.add_css_class("card")
        new_inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, vexpand=True
        )
        new_inner.append(label("+", "name", xalign=0.5))
        new_inner.append(label("New theme", "name", xalign=0.5))
        new_card.set_child(new_inner)
        new_card.connect("clicked", lambda _b: self.open_editor(None))
        flow.append(new_card)
        for tid, name, character in palette.available():
            colors = palette.load(tid)
            custom = bool((palette.read(tid) or {}).get("custom"))
            b = Gtk.Button(can_focus=True)
            b.add_css_class("card")
            if tid == current:
                b.add_css_class("current")
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            inner.append(swatch(colors))
            top = Gtk.Box(spacing=6)
            top.append(label(name, "name", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            if tid == current:
                top.append(label("in use", "badge"))
            inner.append(top)
            inner.append(
                label(
                    character or ("Your own theme" if custom else "The original Everforest look"),
                    "char",
                    xalign=0,
                    ellipsize=Pango.EllipsizeMode.END,
                )
            )
            b.set_child(inner)
            b.connect("clicked", lambda _b, t=tid: self.pick_theme(t))
            if custom:
                wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                wrap.append(b)
                actions = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
                edit_btn = Gtk.Button(label="Edit")
                edit_btn.add_css_class("act")
                edit_btn.connect("clicked", lambda _b, t=tid: self.open_editor(t))
                actions.append(edit_btn)
                actions.append(self.rename_button(tid, name))
                actions.append(self.delete_button(tid, name))
                wrap.append(actions)
                flow.append(wrap)
            else:
                flow.append(b)
        box.append(flow)
        return box

    def rename_button(self, theme_id, name):
        """A button whose popover renames a custom theme in place."""
        mb = Gtk.MenuButton(label="Rename")
        mb.add_css_class("act")
        popover = Gtk.Popover()
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=10,
            margin_bottom=10,
            margin_start=10,
            margin_end=10,
        )
        entry = Gtk.Entry(text=name, width_chars=18)
        error = label("", "error", xalign=0, wrap=True, visible=False)
        save = Gtk.Button(label="Save")
        save.add_css_class("act")
        save.add_css_class("primary")

        def validate(*_a):
            problem = theme_maker.check_name(entry.get_text(), exclude_id=theme_id)
            error.set_label(problem or "")
            error.set_visible(bool(problem))
            save.set_sensitive(problem is None)
            return problem

        def do_rename(_w):
            if validate():
                return
            theme_maker.rename(theme_id, entry.get_text())
            popover.popdown()
            self.rebuild("theme")

        entry.connect("changed", validate)
        entry.connect("activate", do_rename)
        save.connect("clicked", do_rename)
        box.append(entry)
        box.append(error)
        box.append(save)
        popover.set_child(box)
        mb.set_popover(popover)
        return mb

    def delete_button(self, theme_id, name):
        """A button whose popover asks for confirmation, then deletes a custom theme."""
        mb = Gtk.MenuButton(label="Delete")
        mb.add_css_class("act")
        popover = Gtk.Popover()
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=10,
            margin_bottom=10,
            margin_start=10,
            margin_end=10,
        )
        box.append(label(f"Delete “{name}”? This can't be undone.", "desc", xalign=0, wrap=True))
        actions = Gtk.Box(spacing=8)
        cancel = Gtk.Button(label="Cancel")
        cancel.add_css_class("act")
        cancel.connect("clicked", lambda _b: popover.popdown())
        confirm = Gtk.Button(label="Delete")
        confirm.add_css_class("act")

        def do_delete(_b):
            if self.busy:
                return
            self.busy = True
            popover.popdown()

            def work():
                theme_maker.delete(
                    theme_id,
                    apply=lambda tid: subprocess.run(
                        [THEME_PY, "apply", tid], capture_output=True, timeout=20
                    ),
                )

            def done(_r):
                self.busy = False
                self.apply_css()
                self.rebuild("theme")
                self.rebuild("wallpaper")

            in_background(work, done)

        confirm.connect("clicked", do_delete)
        actions.append(cancel)
        actions.append(confirm)
        box.append(actions)
        popover.set_child(box)
        mb.set_popover(popover)
        return mb

    def pick_theme(self, tid):
        if self.busy or tid == palette.current():
            return  # one switch at a time: the last click must be the theme you get
        self.busy = True

        def done(_r):
            self.busy = False
            self.apply_css()
            self.rebuild("theme")
            self.rebuild("wallpaper")

        in_background(lambda: subprocess.run([THEME_PY, "apply", tid], capture_output=True, timeout=20), done)

    # ----- theme editor --------------------------------------------------------------
    def open_editor(self, theme_id):
        """The editor page: a new theme when theme_id is None, else edit a custom one.
        Not a sidebar entry: reached from the Theme page's New theme, Edit and Rename."""
        if theme_id is not None and not (palette.read(theme_id) or {}).get("custom"):
            theme_id = None  # a built-in theme (e.g. `settings.py theme-edit-luffy`): make a new one
        old = self.stack.get_child_by_name("editor")
        if old is not None:
            self.stack.remove(old)
        self.stack.add_named(self.scrolled(self.editor_page(theme_id)), "editor")
        self.show_page("editor")

    def color_row(self, title, button):
        row = Gtk.Box(spacing=12)
        row.add_css_class("row")
        row.append(label(title, "title", xalign=0, hexpand=True))
        row.append(button)
        return row

    def editor_page(self, theme_id):
        editing = theme_id is not None
        if editing:
            data = palette.read(theme_id) or {}
            saved = dict(data.get("colors", {}))
            name0 = data.get("name", "")
            bg, fg, accent, accent2 = (
                saved.get("bg0", "#2d353b"),
                saved.get("fg", "#d3c6aa"),
                saved.get("green", "#a7c080"),
                saved.get("blue", "#7fbbb3"),
            )
            derived0 = theme_maker.derive(bg, fg, accent, accent2)
            overrides = {k: v for k, v in saved.items() if k != "shadow" and derived0.get(k) != v}
        else:
            live = palette.load(palette.current())
            bg, fg, accent, accent2 = live["bg0"], live["fg"], live["green"], live["blue"]
            name0, overrides = "", {}
        picks = {"bg": bg, "fg": fg, "accent": accent, "accent2": accent2}

        box = self.page_box(
            "Edit theme" if editing else "New theme",
            "Four colors become a full, readable theme. Open Advanced to change any one "
            "of the colors it derives.",
        )

        name_row = Gtk.Box(spacing=12)
        name_row.add_css_class("row")
        name_entry = Gtk.Entry(text=name0, hexpand=True, placeholder_text="Theme name")
        name_row.append(name_entry)
        box.append(name_row)
        name_error = label("", "error", xalign=0, wrap=True, visible=False)
        box.append(name_error)

        def current_colors():
            colors = theme_maker.derive(picks["bg"], picks["fg"], picks["accent"], picks["accent2"])
            colors.update(overrides)
            return colors

        colors0 = current_colors()
        preview = theme_preview(colors0)
        advanced_areas = {}

        def refresh():
            colors = current_colors()
            preview.colors = colors
            preview.queue_draw()
            for role, area in advanced_areas.items():
                area.color = colors[role]
                area.queue_draw()

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("act")
        save_btn.add_css_class("primary")

        def validate():
            problem = theme_maker.check_name(name_entry.get_text(), exclude_id=theme_id)
            name_error.set_label(problem or "")
            name_error.set_visible(bool(problem))
            save_btn.set_sensitive(problem is None and not self.busy)
            return problem

        name_entry.connect("changed", lambda *_: validate())

        def pick_main(key):
            def on_pick(hex_color):
                picks[key] = hex_color
                refresh()

            return on_pick

        box.append(label("COLORS", "section", xalign=0))
        self.editor_choosers = {}
        for key, title in (
            ("bg", "Background"),
            ("fg", "Text"),
            ("accent", "Main accent"),
            ("accent2", "Second accent"),
        ):
            btn, chooser = color_button(picks[key], pick_main(key))
            self.editor_choosers[key] = chooser
            box.append(self.color_row(title, btn))

        box.append(label("PREVIEW", "section", xalign=0))
        box.append(preview)

        expander = Gtk.Expander(label="Advanced")
        adv_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        reset_btn = Gtk.Button(label="Reset", halign=Gtk.Align.START)
        reset_btn.add_css_class("act")

        def do_reset(_b):
            overrides.clear()
            refresh()

        reset_btn.connect("clicked", do_reset)
        adv_box.append(reset_btn)

        def pick_role(role):
            def on_pick(hex_color):
                overrides[role] = hex_color
                refresh()

            return on_pick

        for role, value in colors0.items():
            if role == "shadow":
                continue
            btn, _chooser = color_button(value, pick_role(role))
            adv_box.append(self.color_row(role, btn))
            advanced_areas[role] = btn.get_child()  # the button's swatch: refresh() redraws it
        expander.set_child(adv_box)
        box.append(expander)

        def do_save(_b):
            problem = validate()
            if problem or self.busy:
                return
            self.busy = True
            save_btn.set_sensitive(False)
            name = name_entry.get_text()
            colors = current_colors()

            def work():
                new_id = theme_maker.save(name, colors, theme_id=theme_id)
                subprocess.run([THEME_PY, "apply", new_id], capture_output=True, timeout=20)
                return new_id

            def done(result):
                self.busy = False
                if isinstance(result, Exception):
                    name_error.set_label(f"Couldn't save: {result}")
                    name_error.set_visible(True)
                    validate()
                    return
                self.apply_css()
                self.rebuild("theme")
                self.rebuild("wallpaper")
                self.show_page("theme")

            in_background(work, done)

        save_btn.connect("clicked", do_save)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.add_css_class("act")
        cancel_btn.connect("clicked", lambda *_: self.show_page("theme"))
        acts = Gtk.Box(spacing=8, margin_top=14, halign=Gtk.Align.END)
        acts.append(cancel_btn)
        acts.append(save_btn)
        box.append(acts)

        validate()
        return box

    # ----- wallpaper -----------------------------------------------------------------
    def wallpaper_page(self):
        box = self.page_box(
            "Wallpaper",
            "One picture for every theme. Use images you may use (fan art: check the "
            "artist's terms). With none, the desktop is the theme's color.",
        )
        if getattr(self, "wall_error", None):
            box.append(label(self.wall_error, "error", xalign=0, wrap=True))
            self.wall_error = None
        path = palette.wallpaper()
        row = Gtk.Box(spacing=14)
        row.add_css_class("row")
        if path:
            pic = Gtk.Picture.new_for_filename(path)
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_size_request(128, 72)
            pic.set_overflow(Gtk.Overflow.HIDDEN)
            pic.add_css_class("thumb")
            row.append(pic)
        else:
            plain = swatch(palette.load(palette.current()), names=("bg0",))
            plain.set_size_request(128, 72)
            plain.set_hexpand(False)
            row.append(plain)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER, hexpand=True)
        text.append(label("Wallpaper", "title", xalign=0))
        text.append(
            label(
                os.path.basename(path) if path else "Plain color",
                "desc",
                xalign=0,
                ellipsize=Pango.EllipsizeMode.MIDDLE,
            )
        )
        row.append(text)
        choose = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        choose.add_css_class("act")
        choose.connect("clicked", lambda _b: self.choose_wallpaper())
        remove = Gtk.Button(label="Remove", valign=Gtk.Align.CENTER, sensitive=bool(path))
        remove.add_css_class("act")
        remove.connect("clicked", lambda _b: self.set_wallpaper(None))
        row.append(choose)
        row.append(remove)
        box.append(row)
        return box

    def choose_wallpaper(self):
        images = Gtk.FileFilter(name="Images (PNG, JPEG, WebP)")
        for mime in IMAGE_TYPES:
            images.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(images)
        dialog = Gtk.FileDialog(title="Wallpaper", filters=filters, default_filter=images)
        pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
        if pictures and os.path.isdir(pictures):
            dialog.set_initial_folder(Gio.File.new_for_path(pictures))

        def picked(d, result):
            try:
                f = d.open_finish(result)
            except GLib.Error:
                return  # cancelled
            if f and f.get_path():
                self.set_wallpaper(f.get_path())

        dialog.open(self.win, None, picked)

    def set_wallpaper(self, source):
        """Copy source in as the one wallpaper (None removes it), then show it."""
        ext = os.path.splitext(source)[1].lower() if source else ""
        if self.busy or (source and ext not in palette.WALLPAPER_EXTS):
            return
        self.busy = True

        def work():
            palette.set_wallpaper(source)
            subprocess.run([THEME_PY, "apply", palette.current()], capture_output=True, timeout=20)

        def done(result):
            self.busy = False
            if isinstance(result, Exception):
                self.wall_error = f"Couldn't use that picture: {result}"
            self.rebuild("wallpaper")

        in_background(work, done)

    # ----- notifications ------------------------------------------------------------------
    def notifications_page(self):
        box = self.page_box("Notifications", "Pop-ups from apps. The bell on the bar shows them all.")
        row, _text = self.row("Do Not Disturb", "No pop-ups; they still wait in the list.")
        self.dnd = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.dnd_updating = False
        self.dnd.connect("notify::active", self.on_dnd)
        row.append(self.dnd)
        box.append(row)
        row, self.count_text = self.row("Waiting", "")
        clear = Gtk.Button(label="Clear all", valign=Gtk.Align.CENTER)
        clear.add_css_class("act")
        clear.connect("clicked", lambda *_: in_background(lambda: swaync("-C"), lambda _r: self.read_notifications()))
        row.append(clear)
        box.append(row)
        self.read_notifications()
        return box

    def read_notifications(self):
        def done(result):
            dnd, count = result if isinstance(result, tuple) else ("", "")
            self.dnd_updating = True
            self.dnd.set_active(dnd == "true")
            self.dnd_updating = False
            desc = self.count_text.get_last_child()
            desc.set_label(
                "Notifications aren't running (swaync)." if not count.isdigit()
                else "Nothing waiting." if count == "0"
                else f"{count} notification{'s' * (count != '1')} in the list."
            )

        in_background(lambda: (swaync("-D"), swaync("-c")), done)

    def on_dnd(self, sw, _p):
        if not self.dnd_updating:
            flag = "-dn" if sw.get_active() else "-df"
            in_background(lambda: swaync(flag), lambda _r: self.read_notifications())

    # ----- input & behavior ----------------------------------------------------------------
    def keyboard_page(self):
        box = self.page_box(
            "Keyboard & touchpad",
            "Saved in ~/.config/hypr/user-settings.json and applied "
            "at once (the bar blinks while Hyprland reloads).",
        )
        s = store.load()

        box.append(label("KEYBOARD", "section", xalign=0))
        row, text = self.row(
            "Keyboard layouts",
            "In switching order, separated by commas. " "Alt+Shift or SUPER+Space switches.",
        )
        entry = Gtk.Entry(text=s["kb_layout"], valign=Gtk.Align.CENTER, width_chars=12)
        apply_btn = Gtk.Button(label="Apply", valign=Gtk.Align.CENTER)
        apply_btn.add_css_class("act")
        apply_btn.add_css_class("primary")
        self.error = label("", "error", xalign=0, wrap=True, visible=False)
        text.append(self.error)
        apply_btn.connect("clicked", lambda *_: self.save(kb_layout=entry.get_text()))
        entry.connect("activate", lambda *_: self.save(kb_layout=entry.get_text()))
        row.append(entry)
        row.append(apply_btn)
        box.append(row)

        box.append(label("TOUCHPAD", "section", xalign=0))
        box.append(
            self.switch_row("Natural scrolling", "Content moves with your fingers.", s, "natural_scroll")
        )
        box.append(self.switch_row("Tap to click", "A light tap is a click.", s, "tap_to_click"))
        return box

    def look_page(self):
        box = self.page_box(
            "Look & behavior",
            "Saved in ~/.config/hypr/user-settings.json and applied at once. "
            "The sleep timer is on Power & sleep.",
        )
        s = store.load()
        box.append(
            self.switch_row(
                "Gaps and rounded corners",
                "Space between windows (SUPER+H hides it " "until the next reload).",
                s,
                "gaps",
            )
        )
        box.append(self.switch_row("Animations", "Windows and desks slide and fade.", s, "animations"))
        return box

    def row(self, title, desc):
        row = Gtk.Box(spacing=12)
        row.add_css_class("row")
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        text.append(label(title, "title", xalign=0))
        text.append(label(desc, "desc", xalign=0, wrap=True))
        row.append(text)
        return row, text

    def switch_row(self, title, desc, s, key):
        row, _text = self.row(title, desc)
        sw = Gtk.Switch(active=s[key], valign=Gtk.Align.CENTER)
        sw.connect("notify::active", lambda w, _p: self.save(**{key: w.get_active()}))
        row.append(sw)
        return row

    def save(self, **changes):
        # Hyprland reloads by itself when user-settings.lua changes, but only watches
        # it once it has loaded it: the first time, ask for the reload
        first = not os.path.exists(store.paths()[1])
        try:
            store.save(dict(store.load(), **changes))
        except (ValueError, OSError) as e:
            self.error.set_label(str(e))
            self.error.set_visible(True)
            return
        self.error.set_visible(False)
        if first:
            spawn(["hyprctl", "reload"])


class PageHost:
    """What a panel sees of Settings (see panel.py)."""

    embedded = True

    def __init__(self, app, key):
        self.app, self.key = app, key

    def close(self):
        pass  # Settings stays open

    def is_shown(self):
        return self.app.win.get_visible() and self.app.page == self.key


if __name__ == "__main__":
    sys.exit(Settings().run(sys.argv))
