# Summer Hyprland

An Everforest desktop for **Hyprland 0.56+** (Lua config), built on
[**summer-day-and-night** by MathisP75](https://github.com/MathisP75/summer-day-and-night) —
thank you for the original design and wallpapers! ☀️🌙

It keeps that look and adds a set of fast, keyboard-friendly popups written in
Python + GTK4, a "one desk across all monitors" workflow, and a one-command installer
for **Fedora, Arch, Ubuntu and Kubuntu**. The logo in the bar's left corner follows
your distro automatically.

## Features

| Keys | What |
|---|---|
| `SUPER+D` (or the logo button) | **Search everything**, like Spotlight: apps, open windows, files and folders (names *and* contents), actions (Wi-Fi, lock, reboot…), math and unit conversions, web search. Tabs: All · Apps · Windows · Files · Actions |
| `SUPER+C` | Calculator (qalc): Standard, Scientific, Programmer, Converter, Date |
| `SUPER+V` | Clipboard history: filters, **pin** text and pictures (`Ctrl+P`) |
| `SUPER+.` | Emoji picker (Unicode 18), pastes into the app you were using |
| `SUPER+N` | Notifications (swaync) |
| `SUPER+L` | Lock (hyprlock) |
| `SUPER+B` | Power menu |
| `SUPER+1…0` | Desk 1–10 — **every monitor switches together** |
| `SUPER+Right/Left` | Cycle through the windows of this desk, across monitors |
| `SUPER+Space`, `Alt+Shift` | Next keyboard layout (on every keyboard at once) |

From the bar:
- **Sound**: per-app volume, **choose the speaker for each app** (e.g. YouTube on the
  speakers, music on the headset), and a swipeable **Now Playing** carousel with
  every player and browser tab.
- **Quick settings**: battery and power mode, Wi-Fi, Bluetooth devices (with their
  battery), Do Not Disturb, stay awake, screen brightness (DDC/CI for external screens).
- **Calendar**: Gregorian / Persian (Solar Hijri) with weather; **world clock**.
- **Idle timer**: lock / sleep after N minutes, or stay awake.

Every popup opens instantly (they stay running hidden), closes with `Esc` or a click
**anywhere on any screen**, and switches tabs with `Tab` / `Shift+Tab`.

## Supported systems

| Distro | Versions | Hyprland 0.56+ from |
|---|---|---|
| Fedora | 44+ | [lionheartp/Hyprland](https://copr.fedorainfracloud.org/coprs/lionheartp/Hyprland/) COPR |
| Arch (and Arch-based) | rolling | official `extra` repo |
| Ubuntu / Kubuntu | 26.04 LTS+ | [cppiber/hyprland](https://launchpad.net/~cppiber/+archive/ubuntu/hyprland) PPA |

Ubuntu 24.04 isn't supported: it has no `gtk4-layer-shell`, which every popup needs.
On other distros, install the packages yourself (see `install.sh` for the list) and
run `./install.sh --configs-only`.

## Install

```sh
git clone https://github.com/<you>/summer-hyprland
cd summer-hyprland
./install.sh            # --dry-run shows what it would do; --theme day for the light theme
```

The installer:
1. installs the packages (asks for `sudo`), plus the JetBrainsMono Nerd Font if missing;
2. moves your current `~/.config/hypr`, `waybar` and `swaync` into
   `~/.config/summer-hyprland-backup-<date>/`;
3. copies the configs and downloads the wallpapers from the original rice.

Then log out and choose **Hyprland** on the login screen (GDM, SDDM, …).

To undo: delete `~/.config/{hypr,waybar,swaync}` and move the folders back out of the
backup.

## Make it yours

- **Theme**: in `~/.config/hypr/hyprland.lua` set `themeName` to `"summer-night"` or
  `"summer-day"`, then save (Hyprland reloads by itself).
- **Monitors**: see the *Monitors* section of `hyprland.lua`. `hyprctl monitors` shows
  each screen's description; `HOME_SLOTS` pins external screens to a desk block.
- **Compact bar on a vertical screen**: add a second bar to
  `~/.config/waybar/everforest/config` and exclude that screen from the first one:
  ```jsonc
  [
    { "output": ["!DP-1", "*"], /* …the normal bar… */ },
    { "output": "DP-1", "width": 440, "height": 60, "layer": "top", "position": "top",
      "modules-center": ["group/desks"],
      "include": ["~/.config/waybar/everforest/modules.jsonc"] }
  ]
  ```
- **Lock screen picture**: save any square image as `~/.face`.
- **Bar logo**: detected from `/etc/os-release`; force one with
  `echo arch > ~/.config/waybar/distro`.
- **Brightness of external screens** uses DDC/CI: your user may need to be in the
  `i2c` group (`sudo usermod -aG i2c $USER`).

## Credits

- [**summer-day-and-night**](https://github.com/MathisP75/summer-day-and-night) by
  **MathisP75** — the original rice: design, bar style, colors and wallpapers.
- [Everforest](https://github.com/sainnhe/everforest) color scheme by sainnhe.
- [Hyprland](https://hyprland.org), [Waybar](https://github.com/Alexays/Waybar),
  [SwayNotificationCenter](https://github.com/ErikReider/SwayNotificationCenter),
  [gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell),
  [Qalculate!](https://qalculate.github.io), [cliphist](https://github.com/sentriz/cliphist).
- Emoji data © Unicode, Inc. and [wofi-emoji](https://github.com/Zeioth/wofi-emoji) —
  see [THIRD-PARTY.md](THIRD-PARTY.md).

## License

[MIT](LICENSE) for this project's code. The original rice's files (wallpapers, kitty
colors) are downloaded from its repository and remain its author's; see
[THIRD-PARTY.md](THIRD-PARTY.md).
