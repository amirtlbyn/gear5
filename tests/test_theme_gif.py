"""A theme's GIF file (roadmap 6.2, spec GIFT; the bar's part is tests/test_gif.py).
See config/waybar/scripts/theme_gif.py, theme.py (write_all, write_bar) and
config/hypr/themes/README.md."""

import shutil
import subprocess

import pytest
import settings_store as store
import theme
import theme_gif
from conftest import ROOT, THEMES


def test_the_gif_of_a_theme_is_in_the_themes_folder_under_its_id(tmp_path):
    """GIFT-5: given a GIF in themes/ and another in characters/, when the GIF of a
    theme is looked up, then it is themes/<id>.gif; the old file is not found, and an
    id that is not a plain name finds nothing."""
    themes = tmp_path / "hypr" / "themes"
    characters = tmp_path / "hypr" / "characters"
    themes.mkdir(parents=True)
    characters.mkdir()
    (themes / "zoro.gif").write_bytes(b"GIF89a")
    (characters / "nami.sticker.gif").write_bytes(b"GIF89a")

    assert theme_gif.gif("zoro", str(themes)) == str(themes / "zoro.gif")
    assert theme_gif.gif("nami", str(themes)) is None
    assert theme_gif.gif("../zoro", str(themes)) is None


def test_the_old_gifs_move_to_themes_and_never_overwrite_one_there(tmp_path):
    """GIFT-10: given characters/<id>.sticker.gif files, when a theme is applied,
    then each moves to themes/<id>.gif; when themes/<id>.gif exists, then it keeps its
    bytes and the old file stays where it is; a lock picture in characters/ is
    left alone. The move runs once: a GIF removed afterwards does not come back."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    characters = tmp_path / "hypr" / "characters"
    characters.mkdir()
    (characters / "zoro.sticker.gif").write_bytes(b"GIF89a old zoro")
    (characters / "nami.sticker.gif").write_bytes(b"GIF89a old nami")
    (characters / "zoro.png").write_bytes(b"lock picture")
    (tmp_path / "hypr" / "themes" / "nami.gif").write_bytes(b"GIF89a new nami")

    theme.write_all("zoro", str(tmp_path))

    themes = tmp_path / "hypr" / "themes"
    assert (themes / "zoro.gif").read_bytes() == b"GIF89a old zoro"
    assert not (characters / "zoro.sticker.gif").exists()
    assert (themes / "nami.gif").read_bytes() == b"GIF89a new nami"
    assert (characters / "nami.sticker.gif").read_bytes() == b"GIF89a old nami"
    assert (characters / "zoro.png").read_bytes() == b"lock picture"

    theme_gif.set_gif("nami", None, str(themes))
    theme.write_all("zoro", str(tmp_path))
    assert not (themes / "nami.gif").exists()


def test_a_theme_write_nudges_the_bar_player(tmp_path, monkeypatch, bar_signals):
    """Regression (spec CHAR-3, kept for the GIF): given an installed config, when a
    theme is written, then the bar's player is nudged once, and nothing calls
    Hyprland."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    (tmp_path / "hypr" / "themes" / "current").write_text("zoro\n")
    commands = []
    monkeypatch.setattr(theme, "run", commands.append)
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS))

    theme.write_all("zoro", str(tmp_path))

    assert bar_signals == ["USR1"]
    assert not [c for c in commands if c[0] == "hyprctl"]


def test_a_failed_frame_making_does_not_stop_the_theme_switch(tmp_path, monkeypatch, bar_signals):
    """Regression (spec GIF, review of session 1): given a system where the frames cannot be made, when a
    theme is written, then every theme file is still written and the bar's player
    gets no nudge."""
    shutil.copytree(THEMES, tmp_path / "hypr" / "themes")
    monkeypatch.setattr(theme, "run", lambda argv: "")
    monkeypatch.setattr(store, "load", lambda: dict(store.DEFAULTS))

    def no_pixbuf(*_args):
        raise ImportError("No module named 'gi'")

    monkeypatch.setattr(theme_gif, "make_frames", no_pixbuf)

    theme.write_all("zoro", str(tmp_path))

    assert (tmp_path / "hypr" / "themes" / "current").read_text() == "zoro\n"
    assert (tmp_path / "hypr" / "themes" / "current.lua").exists()
    assert bar_signals == []


def test_a_gif_is_copied_whole_or_refused_and_remove_deletes_it(tmp_path):
    """CHAR-9: given a theme, when a GIF is picked, then it is copied to
    themes/<id>.gif; when the file is not a GIF, or is 8 MB + 1, then it is refused
    with a message and the old GIF stays; when the copy fails, then the old GIF stays
    and no .part file is left; when Remove runs, then the GIF is gone."""
    themes = tmp_path / "hypr" / "themes"
    themes.mkdir(parents=True)
    gif = tmp_path / "new.gif"
    gif.write_bytes(b"GIF89a new")
    not_gif = tmp_path / "fake.gif"
    not_gif.write_bytes(b"\x89PNG not a gif")
    big = tmp_path / "big.gif"
    big.write_bytes(b"GIF89a" + b"0" * (theme_gif.MAX_GIF_BYTES - 5))

    theme_gif.set_gif("zoro", str(gif), str(themes))
    assert (themes / "zoro.gif").read_bytes() == b"GIF89a new"

    with pytest.raises(ValueError, match="GIF"):
        theme_gif.set_gif("zoro", str(not_gif), str(themes))
    with pytest.raises(ValueError, match="8 MB"):
        theme_gif.set_gif("zoro", str(big), str(themes))
    with pytest.raises(OSError):
        theme_gif.set_gif("zoro", str(tmp_path / "missing.gif"), str(themes))
    assert (themes / "zoro.gif").read_bytes() == b"GIF89a new"
    assert not (themes / "zoro.gif.part").exists()

    theme_gif.set_gif("zoro", None, str(themes))
    assert not (themes / "zoro.gif").exists()


def test_deleting_a_custom_theme_drops_its_gif_only(tmp_path):
    """CHAR-11: given a custom theme with a GIF, when it is deleted, then its GIF is
    gone and another theme's GIF is kept."""
    import theme_maker

    themes = tmp_path / "hypr" / "themes"
    shutil.copytree(THEMES, themes)
    colors = theme_maker.derive("#2d353b", "#d3c6aa", "#a7c080", "#7fbbb3")
    theme_id = theme_maker.save("Nika", colors, themes=str(themes))
    (themes / f"{theme_id}.gif").write_bytes(b"GIF89a")
    (themes / "zoro.gif").write_bytes(b"GIF89a")

    theme_maker.delete(theme_id, themes=str(themes))

    assert not (themes / f"{theme_id}.gif").exists()
    assert (themes / "zoro.gif").exists()


def test_a_theme_gif_is_not_tracked_by_git():
    """GIFT-11: given the repository's ignore rules, when a GIF is put in
    config/hypr/themes/, then git ignores it, and a theme file is not ignored."""
    def ignored(path):
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False).returncode == 0

    assert ignored("config/hypr/themes/zoro.gif")
    assert not ignored("config/hypr/themes/zoro.json")
