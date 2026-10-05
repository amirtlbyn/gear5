#!/usr/bin/env python3
"""
The desktop's two fonts — the English (mono) family and the Persian one —
chosen on the Settings Fonts page and kept in user-settings.json (see
settings_store.py). The defaults below are also the names hardcoded in every
popup's CSS, so with nothing saved, swap() replaces a name with itself.

    import fonts
    css = fonts.swap(STYLE)             # a popup's CSS, in the chosen fonts
    desc = fonts.pango("…Bold 11")      # the same, for Pango descriptions
    fonts.css_rule()                    # the * font-family rule theme.py writes
"""

import settings_store as store

EN, FA = "JetBrainsMono Nerd Font", "Vazirmatn"


def families():
    """(english, persian) family names: the saved choice, or the defaults."""
    s = store.load()
    return s["font_en"], s["font_fa"]


def swap(css):
    """The chosen families in place of the default ones, in a popup's CSS.
    Only the two quoted default names are touched, so a rule never loses its
    font (a chosen name that equals the default leaves the CSS untouched)."""
    en, fa = families()
    return css.replace(f'"{EN}"', f'"{en}"').replace(f'"{FA}"', f'"{fa}"')


def pango(desc):
    """The same swap for a Pango font description string (unquoted names)."""
    en, fa = families()
    return desc.replace(EN, en).replace(FA, fa)


def css_rule():
    """The font-family rule theme.py appends to the generated colors file that
    the bar and swaync import; their own * rules carry no font any more."""
    en, fa = families()
    return f'* {{ font-family: "{en}", "{fa}", FontAwesome, sans-serif; }}\n'


def kitty_font():
    """kitty's font lines for its generated colors file: one family, and the
    Persian ranges mapped onto the Persian font (kitty has no fallback list)."""
    en, fa = families()
    return (
        f"font_family      {en}\n"
        "symbol_map U+0600-U+06FF,U+200C-U+200D,U+FB50-U+FDFF,U+FE70-U+FEFF "
        f"{fa}\n"
    )
