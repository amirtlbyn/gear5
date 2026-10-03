"""docs/SCREENSHOTS.md: every image it links must exist, and the README must link it."""

import os
import re
import subprocess

from conftest import ROOT

DOCS = os.path.join(ROOT, "docs")
PAGE = os.path.join(DOCS, "SCREENSHOTS.md")
# the project's name before "Gear5", in pieces so this file does not carry it whole
# (the project-name test below scans every tracked file for it)
OLD_NAMES = ("Summer" + " Hyprland", "summer" + "-hyprland")
KEPT_NAMES = ("summer-day-and-night", "Summer night")  # the upstream rice, the theme


def test_screenshot_links_resolve_and_readme_links_the_page():
    """GEAR-17: given docs/SCREENSHOTS.md, when its image links and the README are
    read, then every image link resolves to a file under docs/, and the README
    links docs/SCREENSHOTS.md."""
    text = open(PAGE, encoding="utf-8").read()
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert links
    missing = [link for link in links if not os.path.isfile(os.path.join(DOCS, link))]
    assert not missing, missing
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "docs/SCREENSHOTS.md" in readme


def test_docs_describe_the_power_page_and_its_new_shots():
    """G5-7: given README.md and docs/SCREENSHOTS.md, when the power page became
    the power mode and the sleep actions (the battery and brightness moved to
    their own pages), then both describe it that way and link the power popup
    and Power & sleep screenshots."""
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "power mode, the sleep timer" in readme
    assert "lock / sleep / reboot / power off" in readme
    shots = open(PAGE, encoding="utf-8").read()
    power = shots.split("### Power & sleep", 1)[1].split("###", 1)[0]
    assert "Power mode" in power and "eboot" in power
    for stem in ("settings-power", "popup-power"):
        assert f"screenshots/{stem}.png" in shots


def test_screenshots_page_shows_the_reorganized_pages():
    """SHOT-1: given docs/SCREENSHOTS.md, when the battery and the brightness
    moved pages (BATT, BRT), then the Power & sleep section promises neither
    (the old words are gone), the Settings Displays section names the selected
    screen's brightness, and the Battery and minimized-picker sections link
    their shots with no pending notes left."""
    shots = open(PAGE, encoding="utf-8").read()
    power = shots.split("### Power & sleep", 1)[1].split("###", 1)[0]
    assert "Power mode" in power and "Battery and power mode" not in power
    displays = shots.split("### Displays", 2)[2].split("###", 1)[0]
    assert "brightness" in displays
    assert "screenshots/settings-battery.png" in shots
    assert "screenshots/popup-minimized-picker.png" in shots
    assert "pending" not in shots


def test_readme_sends_each_setting_to_its_page():
    """SHOT-2: given README.md, when a reader looks for the battery or a screen's
    brightness, then the Settings row and the Everything-else bullet send the
    battery (level, health, limits) to Battery, the brightness to Displays, and
    the power mode to Power & sleep."""
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    row = next(line for line in readme.splitlines() if "SUPER+I" in line)
    assert "**Battery** (level, health" in row and "per-screen brightness" in row
    bullet = readme.split("**Everything else**", 1)[1].split("\n- ", 1)[0]
    assert "each screen's" in bullet and "power mode, the sleep" in bullet
    assert "**Battery** (level, health," in bullet
    assert "battery, power mode, brightness of every screen" not in readme


def test_readme_describes_the_fonts_page_and_kitty_theming():
    """FONT-5: given README.md, when the Fonts page and kitty theming landed,
    then the Settings row and Make-it-yours describe both."""
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert "fonts (English + Persian)" in readme
    assert "**Fonts**: `SUPER+I` → Fonts" in readme
    assert "kitty's colors all switch too" in readme


def _tracked_text_files():
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, cwd=ROOT)
    for path in out.stdout.splitlines():
        try:
            with open(os.path.join(ROOT, path), "rb") as f:
                f.read().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binary or unreadable: not a file that names the project
        yield os.path.join(ROOT, path)


def test_project_name_is_gear5_everywhere():
    """G5-1: given every tracked file outside .claude/, when it is read, then none
    calls the project by its old name (OLD_NAMES above), while the upstream
    rice (summer-day-and-night) and the theme (Summer night) keep their names."""
    offenders = []
    for path in _tracked_text_files():
        if ".claude/" in path.replace(os.sep, "/"):
            continue  # the specs' work logs talk about the rename itself
        text = open(path, encoding="utf-8").read()
        if any(name in text for name in OLD_NAMES):
            offenders.append(path)
    assert not offenders, offenders
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert readme.startswith("# Gear5")
    assert all(name in readme for name in KEPT_NAMES)


def test_installer_and_readme_name_the_gear5_backup_folder():
    """G5-2: given install.sh and README.md, when the installer backs up existing
    configs, then the folder is ~/.config/gear5-backup-<date>/, named in both."""
    installer = open(os.path.join(ROOT, "install.sh"), encoding="utf-8").read()
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    assert 'backup="$CONFIG/gear5-backup-$stamp"' in installer
    assert "~/.config/gear5-backup-<date>/" in readme
