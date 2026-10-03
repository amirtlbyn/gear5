"""CWPM: the clock popup merges the calendar and the timezone list into one
page, opened from either mouse button, with at most 4 pinned timezones.
CPFU: follow-ups from live use — auto/manual weather city, a 2x2 zone grid,
and EN/FA width and font consistency."""

import os

import weather_lib as wx
from conftest import ROOT, SCRIPTS

CLOCK = os.path.join(SCRIPTS, "worldclock.py")


def read(path):
    return open(path, encoding="utf-8").read()


def test_calendar_popup_script_is_gone_and_merged_into_worldclock():
    """Given the scripts directory, then calendar-popup.py no longer exists —
    its content was ported into worldclock.py, which builds and renders a
    calendar section alongside the pinned zones, in the same popup. See
    test_bar_clock.py for the corresponding acceptance-criterion test."""
    assert not os.path.exists(os.path.join(SCRIPTS, "calendar-popup.py"))
    src = read(CLOCK)
    assert "def build_calendar_section(self, popup):" in src
    assert "def render_calendar(self):" in src
    assert "self.zones_box" in src and "self.grid" in src


def test_pin_is_capped_at_four_zones():
    """CWPM-4: given the merged popup's pin() method, when 4 zones are already
    pinned, then a 5th pin is refused.
    CWPM-5: given fewer than 4 pinned, then pin() still allows another."""
    src = read(CLOCK)
    assert "MAX_PINNED = 4" in src
    pin_body = src.split("def pin(self, z):", 1)[1].split("\n\n", 1)[0]
    assert "len(self.st[\"pinned\"]) < MAX_PINNED" in pin_body


def test_no_popup_sh_or_bar_wiring_left_for_calendar_popup():
    """Given popup.sh and modules.jsonc, then no dispatch target for a
    separate calendar popup remains, and the bar clock's on-click and
    on-click-right both open the same merged popup. See test_bar_clock.py
    for the corresponding acceptance-criterion test."""
    popup_sh = read(os.path.join(SCRIPTS, "popup.sh"))
    assert "calendar-popup" not in popup_sh
    modules = read(os.path.join(ROOT, "config", "waybar", "bar", "modules.jsonc"))
    clock = modules.split('"custom/clock": {', 1)[1].split("},", 1)[0]
    assert clock.count("popup.sh worldclock") == 2


def test_weather_home_defaults_to_auto_and_follows_the_given_zone(tmp_path, monkeypatch):
    """CPFU-2: given no manually-picked city, when the calendar asks for the
    weather home, then it gets the zone it was asked to follow (auto mode),
    and switching which zone that is changes the answer."""
    monkeypatch.setattr(wx, "HOME_FILE", str(tmp_path / "weather-place.json"))
    monkeypatch.setattr(wx, "place", lambda z: (0.0, 0.0))  # every zone/city "exists"
    home = wx.get_home("Asia/Tehran")
    assert home["auto"] is True and home["key"] == "Asia/Tehran"
    home = wx.get_home("Europe/Sofia")
    assert home["auto"] is True and home["key"] == "Europe/Sofia"


def test_weather_home_manual_pick_overrides_until_set_back_to_auto(tmp_path, monkeypatch):
    """CPFU-3: given a manually picked city, when the calendar asks for the
    weather home (regardless of which zone is active), then it keeps
    returning that city, until set_home_auto() switches it back."""
    monkeypatch.setattr(wx, "HOME_FILE", str(tmp_path / "weather-place.json"))
    monkeypatch.setattr(wx, "place", lambda z: (0.0, 0.0))
    wx.set_home({"key": "geo:1,2", "name": "Custom City", "sub": "Somewhere"})
    home = wx.get_home("Asia/Tehran")
    assert home["auto"] is False and home["name"] == "Custom City"
    home = wx.get_home("Europe/Sofia")   # the active zone changed; the manual pick doesn't
    assert home["name"] == "Custom City"
    wx.set_home_auto()
    home = wx.get_home("Europe/Sofia")
    assert home["auto"] is True and home["key"] == "Europe/Sofia"


def test_active_zone_changes_are_wired_to_the_weather_card():
    """Given set_active() and unpin() (the two places the active zone can
    change), then both call refresh_home_weather() so the weather card
    actually follows the change, not just weather_lib's own auto logic in
    isolation; and refresh_home_weather() itself reads the active zone
    (self.st["active"]), not a fixed constant. See
    test_weather_home_defaults_to_auto_and_follows_the_given_zone for the
    corresponding acceptance-criterion test."""
    src = read(CLOCK)
    set_active_body = src.split("def set_active(self, z):", 1)[1].split("\n\n", 1)[0]
    assert "self.refresh_home_weather()" in set_active_body
    unpin_body = src.split("def unpin(self, z):", 1)[1].split("\n\n", 1)[0]
    assert "self.refresh_home_weather()" in unpin_body
    refresh_body = src.split("def refresh_home_weather(self):", 1)[1].split("\n\n", 1)[0]
    assert 'self.st.get("active"' in refresh_body or 'self.st["active"]' in refresh_body


def test_pinned_zones_render_in_a_two_column_grid():
    """CPFU-4: given the pinned-zone section, then it is a Gtk.Grid (not a
    single-column Box), and render() attaches cards two per row."""
    src = read(CLOCK)
    assert 'self.zones_box = Gtk.Grid(' in src
    render_body = src.split("def render(self):", 1)[1].split("\n    def ", 1)[0]
    assert "self.zones_box.attach(card, col, row, 1, 1)" in render_body
    assert "if col == 2:" in render_body


def test_en_and_fa_render_the_same_way():
    """CPFU-5: given every label whose text length depends on language or
    data (the header date, the calendar footer, the weather card, the zone
    cards), then each one caps its width (max_width_chars, or wrap for the
    footer), so none of them can push the popup wider in one language than
    the other; and given FA mode, the popup keeps the EN font (no per-language
    font-family rule), so the text does not change size or shape."""
    src = read(CLOCK)
    for anchor in ("self.header_sub = label(", "self.cal_foot1 = Gtk.Label(",
                  "self.cal_foot2 = Gtk.Label(", "self.cal_wx_now = Gtk.Label(",
                  "self.cal_wx_sub = Gtk.Label(", 'name, "city", xalign=0, hexpand=True'):
        stmt = src.split(anchor, 1)[1].split(")", 1)[0]
        assert "max_width_chars" in stmt or "wrap=True" in stmt, anchor
    assert ".popup.fa" not in src
