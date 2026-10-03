"""
The empty state of a popup's list (roadmap 4.4, spec EMPTY): one sentence, an
optional hint, and an optional button that does the one thing that fills the
list (turn Wi-Fi on, scan again, add a device, ...).

    import empty_state
    empty = empty_state.EmptyState()
    listbox.set_placeholder(empty)
    empty.update("Wi-Fi is off.", button="Turn on Wi-Fi", action=self.turn_on)

Each popup adds CSS below to its own (it uses the theme's color names), so the
three empty states look the same, in the popups and in Settings.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

CSS = """
.empty-state { padding: 20px 8px; }
.empty-text { color: @fg; font-size: 15px; font-weight: bold; }
.empty-hint { color: @grey; font-size: 12px; font-weight: normal; }
button.empty-action {
  background: @green;
  color: @on_accent;
  border: none;
  border-radius: 8px;
  border-bottom: 3px solid @green_edge;
  box-shadow: none;
  padding: 4px 14px;
  margin-top: 4px;
}
button.empty-action:hover { background: alpha(@green, 0.85); }
"""


class EmptyState(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.add_css_class("empty-state")
        self.text = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.text.add_css_class("empty-text")
        self.hint = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER, visible=False)
        self.hint.add_css_class("empty-hint")
        self.button = Gtk.Button(halign=Gtk.Align.CENTER, visible=False)
        self.button.add_css_class("empty-action")
        self.button.connect("clicked", lambda _b: self.action and self.action())
        self.action = None
        for w in (self.text, self.hint, self.button):
            self.append(w)

    def update(self, text, hint="", button="", action=None):
        """Show text, and the hint and the button when given; a button without an
        action is not shown (INV-1: never offer what cannot be done)."""
        self.text.set_label(text)
        self.hint.set_label(hint)
        self.hint.set_visible(bool(hint))
        self.action = action if button else None
        self.button.set_label(button)
        self.button.set_visible(self.action is not None)
