"""A theme's character moment: the glyph and motion of the pop-up sticker, and the
GIF files (roadmap 6.2, spec CHAR; the bar's part is now spec GIF, tests/test_gif.py).
See config/waybar/scripts/moment.py, theme.py (write_all, write_bar) and
config/hypr/themes/README.md."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import moment
import pytest
import settings_store as store
import theme
from conftest import THEMES


def test_built_in_themes_have_known_distinct_glyphs_and_known_motions():
    """CHAR-1: given the twelve built-in theme files, when they are read, then each
    has a glyph from the glyph list (no two the same) and a motion from the motion
    list; and the Nerd Font has every glyph in the list."""
    files = sorted(f for f in os.listdir(THEMES) if f.endswith(".json"))
    data = [json.loads((Path(THEMES) / f).read_text()) for f in files]
    glyphs = [d["glyph"] for d in data]
    assert len(files) == 12
    assert all(g in moment.GLYPHS for g in glyphs)
    assert len(set(glyphs)) == 12
    assert all(d["motion"] in moment.MOTIONS for d in data)
    charset = " ".join(f"{cp:x}" for cp in moment.GLYPHS.values())
    found = subprocess.run(
        ["fc-list", f"{moment.FONT}:charset={charset}", "family"], capture_output=True, text=True, check=False
    ).stdout
    assert found.strip() != ""


def test_a_moment_comes_from_the_choice_then_the_theme_file_then_the_fallback(tmp_path, monkeypatch):
    """CHAR-2: given a theme file, a person's choice and a custom theme, when the
    moment is read, then the glyph and the motion each come from the choice, else
    the file, else the fallback (palette, wobble); an unknown name is skipped."""
    (tmp_path / "zoro.json").write_text('{"glyph": "star", "motion": "spin", "colors": {}}')
    (tmp_path / "custom.json").write_text('{"name": "Custom", "colors": {}}')
    (tmp_path / "typo.json").write_text('{"glyph": "nope", "motion": "sideways", "colors": {}}')
    mine = {"zoro": {"glyph": "heart"}, "typo": {"glyph": 5, "motion": "pop"}}
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS, moments=mine))

    assert moment.moment("zoro", str(tmp_path)) == {"glyph": "heart", "motion": "spin"}
    assert moment.moment("custom", str(tmp_path)) == {"glyph": "palette", "motion": "wobble"}
    assert moment.moment("typo", str(tmp_path)) == {"glyph": "palette", "motion": "pop"}


def test_a_theme_write_nudges_the_bar_player_and_draws_no_glyph(tmp_path, monkeypatch, bar_signals):
    """CHAR-3: given an installed config, when a theme is written, then the bar's
    player is nudged once, no glyph picture or motion CSS is written for the bar, and
    nothing calls Hyprland."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    (tmp_path / "hypr" / "themes" / "current").write_text("zoro\n")
    commands = []
    monkeypatch.setattr(theme, "run", commands.append)
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS))

    theme.write_all("zoro", str(tmp_path))

    assert bar_signals == ["USR1"]
    assert not os.path.exists(os.path.join(moment.CACHE, "sticker.png"))
    assert not (tmp_path / "waybar" / "colors" / "moment.css").exists()
    assert not [c for c in commands if c[0] == "hyprctl"]


def test_a_failed_frame_making_does_not_stop_the_theme_switch(tmp_path, monkeypatch, bar_signals):
    """Review of session 1: given a system where the frames cannot be made, when a
    theme is written, then every theme file is still written and the bar's player
    gets no nudge."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    monkeypatch.setattr(theme, "run", lambda argv: "")
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS))

    def no_pixbuf(*_args):
        raise ImportError("No module named 'gi'")

    monkeypatch.setattr(moment, "make_frames", no_pixbuf)

    theme.write_all("zoro", str(tmp_path))

    assert (tmp_path / "hypr" / "themes" / "current").read_text() == "zoro\n"
    assert (tmp_path / "hypr" / "themes" / "current.lua").exists()
    assert bar_signals == []


@pytest.mark.parametrize("motion", [m for m in moment.MOTIONS if m != "none"])
def test_every_motion_plays_once_in_the_popup(motion):
    """CHAR-5: given a motion, when its CSS is written for the pop-up sticker, then it
    lasts at most 1.2 s and never repeats."""
    ms = moment.MOTIONS[motion][0]
    assert 0 < ms <= moment.MAX_MS
    css = moment.motion_css(motion)
    assert f".sticker-art {{ animation: sticker-{motion} {ms}ms ease-in-out 1; }}" in css
    assert "infinite" not in css


def test_a_gif_is_copied_whole_or_refused_and_remove_deletes_it(tmp_path):
    """CHAR-9: given a theme, when a GIF is picked, then it is copied to
    <id>.sticker.gif and the lock picture is untouched; when the file is not a GIF,
    or is 8 MB + 1, then it is refused with a message and the old GIF stays; when
    the copy fails, then the old GIF stays and no .part file is left; when Remove
    runs, then the GIF is gone."""
    characters = tmp_path / "characters"
    characters.mkdir()
    (characters / "zoro.png").write_bytes(b"lock picture")
    gif = tmp_path / "new.gif"
    gif.write_bytes(b"GIF89a new")
    not_gif = tmp_path / "fake.gif"
    not_gif.write_bytes(b"\x89PNG not a gif")
    big = tmp_path / "big.gif"
    big.write_bytes(b"GIF89a" + b"0" * (moment.MAX_GIF_BYTES - 5))

    moment.set_gif("zoro", str(gif), str(characters))
    assert (characters / "zoro.sticker.gif").read_bytes() == b"GIF89a new"
    assert (characters / "zoro.png").read_bytes() == b"lock picture"

    with pytest.raises(ValueError, match="GIF"):
        moment.set_gif("zoro", str(not_gif), str(characters))
    with pytest.raises(ValueError, match="8 MB"):
        moment.set_gif("zoro", str(big), str(characters))
    with pytest.raises(OSError):
        moment.set_gif("zoro", str(tmp_path / "missing.gif"), str(characters))
    assert (characters / "zoro.sticker.gif").read_bytes() == b"GIF89a new"
    assert not (characters / "zoro.sticker.gif.part").exists()

    moment.set_gif("zoro", None, str(characters))
    assert not (characters / "zoro.sticker.gif").exists()
    assert (characters / "zoro.png").exists()


def test_deleting_a_custom_theme_drops_its_choices_and_its_gif(tmp_path):
    """CHAR-11: given a custom theme with a saved moment and a GIF, when it is
    deleted, then its entry in moments and its GIF are gone, and another theme's
    are kept."""
    import theme_maker

    themes = tmp_path / "hypr" / "themes"
    shutil.copytree(THEMES, themes)
    colors = theme_maker.derive("#2d353b", "#d3c6aa", "#a7c080", "#7fbbb3")
    theme_id = theme_maker.save("Nika", colors, themes=str(themes))
    characters = tmp_path / "hypr" / "characters"
    characters.mkdir()
    (characters / f"{theme_id}.sticker.gif").write_bytes(b"GIF89a")
    (characters / "zoro.sticker.gif").write_bytes(b"GIF89a")
    moments = {theme_id: {"glyph": "star"}, "zoro": {"motion": "spin"}}
    store.save(dict(store.DEFAULTS, moments=moments), str(tmp_path))

    theme_maker.delete(theme_id, themes=str(themes))

    assert store.load(str(tmp_path))["moments"] == {"zoro": {"motion": "spin"}}
    assert not (characters / f"{theme_id}.sticker.gif").exists()
    assert (characters / "zoro.sticker.gif").exists()
