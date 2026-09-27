"""A popup's CSS, scoped for a Settings page: under one root, colors written in, its window rules dropped."""

import re

import panel

STYLE = """
window.wifi-menu { background: transparent; }
.backdrop { background: transparent; }
/* a comment { with braces } */
.popup { background: @bg0; border-bottom: 6px solid @green_edge; }
.popup entry, .popup passwordentry { color: alpha(@fg, 0.5); }
popover > contents { background: shade(@green, 1.1); }
"""
COLORS = {"bg0": "#111111", "fg": "#eeeeee", "green": "#00ff00", "green_edge": "#008800"}


def rules(css):
    return re.findall(r"([^{}]+)\{([^{}]*)\}", css)


def test_every_selector_is_under_the_root():
    css = panel.scoped_css(STYLE, COLORS, "panel-wifi")
    for selectors, _decl in rules(css):
        for s in selectors.split(","):
            assert s.strip().startswith(".panel-wifi "), s


def test_window_and_backdrop_rules_are_left_out():
    css = panel.scoped_css(STYLE, COLORS, "panel-wifi")
    assert "window" not in css
    assert "backdrop" not in css
    assert "comment" not in css


def test_theme_colors_are_written_in():
    css = panel.scoped_css(STYLE, COLORS, "panel-wifi")
    assert "@" not in css
    assert "#008800" in css  # @green_edge, not @green followed by "_edge"
    assert "alpha(#eeeeee, 0.5)" in css
    assert "shade(#00ff00, 1.1)" in css


def test_popup_box_is_flattened_after_its_own_rule():
    css = panel.scoped_css(STYLE, COLORS, "panel-wifi")
    popup_rules = [d for s, d in rules(css) if s.strip() == ".panel-wifi .popup"]
    assert len(popup_rules) == 2
    assert "box-shadow: none" in popup_rules[-1]  # the override comes last, so it wins


def test_scope_keeps_color_names():
    css = panel.scope(".row { background: @bg0; }", "own")
    assert css.strip() == ".own .row { background: @bg0; }"
