"""Every theme must be readable: WCAG contrast for the color pairs the desktop draws."""

import os

import palette
from conftest import THEMES
from theme_maker import PAIRS


def luminance(color):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def theme_ids():
    return sorted(n[:-5] for n in os.listdir(THEMES) if n.endswith(".json"))


def test_there_are_twelve_themes():
    assert len(theme_ids()) == 12
    assert {tid for tid, _n, _c in palette.available(THEMES)} == set(theme_ids())  # all valid


def test_every_theme_is_readable():
    bad = []
    for tid in theme_ids():
        c = palette.load(tid, THEMES)
        for text, bg, minimum in PAIRS:
            ratio = contrast(c[text], c[bg])
            if ratio < minimum:
                bad.append(f"{tid}: {text} on {bg} = {ratio:.2f} (needs {minimum})")
    assert not bad, "\n".join(bad)


def test_every_theme_lists_every_color():
    base = set(palette.read("summer-night", THEMES)["colors"])
    for tid in theme_ids():
        assert set(palette.read(tid, THEMES)["colors"]) == base, tid
