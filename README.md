# Gear5

An Everforest desktop for **Hyprland 0.56+** (Lua config), built on
[**summer-day-and-night** by MathisP75](https://github.com/MathisP75/summer-day-and-night) —
thank you for the original design and wallpapers! ☀️🌙

It keeps that look and adds a set of fast, keyboard-friendly popups written in
Python + GTK4, a "one desk across all monitors" workflow, and a one-command installer
for **Fedora, Arch, Ubuntu and Kubuntu**. The logo in the bar's left corner follows
your distro automatically.

[Screenshots of every app](docs/SCREENSHOTS.md)

## Features

| Keys | What |
|---|---|
| `SUPER+D` (or the logo button) | **Search everything**, like Spotlight: apps, open windows, files and folders (names *and* contents), actions (Wi-Fi, lock, reboot…), math and unit conversions, web search. **New Tab / New Window / New Private Window** for every installed browser, and every app's own actions (e.g. Zen's *New Blank Window*). Tabs: All · Apps · Windows · Minimized · Files · Actions |
| `SUPER+C` | Calculator (qalc): Standard, Scientific, Programmer, Converter, Date |
| `SUPER+V` | Clipboard history: filters, **pin** text and pictures (`Ctrl+P`) |
| `SUPER+.` | Emoji picker (Unicode 18), pastes into the app you were using |
| `SUPER+P` | **Displays**: Laptop only · Extend · Duplicate · External only, drag to arrange, resolution, scale, rotation, mirror. Keep-or-revert in 15 s; layouts are **remembered per set of screens** and come back when you plug them in |
| `SUPER+I` (or *Settings* in the quick settings) | **Settings**: Straw Hat theme, one wallpaper for every theme, an optional GIF for each theme, fonts (English + Persian), displays (per-screen brightness, night light), Wi-Fi, Bluetooth, sound, power & sleep (power mode, the sleep timer), **Battery** (level, health, charge limits: presets, stop/start, speed), notifications, keyboard layouts, touchpad, gaps, animations, the bar background strip, all in one window (no other app opens) |
| `SUPER+A` | **Minimize** the window; the bar shows how many are minimized (click it to open the picker below) |
| `SUPER+-` | Bring back the last minimized window onto the desk you're on (again for the one before) |
| `SUPER+SHIFT+-` | **Minimized windows** picker: a thumbnail card for each, newest first — type to filter, arrows + Enter or its number to bring one back, Delete / middle-click / its × to close it |
| `SUPER+Tab` | **Overview**: every desk with windows, one row each, a thumbnail card per window (then the minimized ones). Click or Enter goes to that window on its desk; `1`…`0` go to a desk; type to filter. Window groups: `SUPER+G` makes one, `SUPER+SHIFT+G` goes to the next window in it |
| `SUPER+N` | Notifications (swaync) |
| `SUPER+L` | Lock (hyprlock) |
| `SUPER+B` | Power menu |
| `SUPER+SHIFT+Esc` | **Unstick**: an open popup that hangs and keeps the keyboard is closed and started again |
| `SUPER+1…0` | Desk 1–10 — **every monitor switches together** |
| `SUPER+Right/Left` | Cycle through the windows of this desk, across monitors |
| `SUPER+Space`, `Alt+Shift` | Next keyboard layout (on every keyboard at once) |

From the bar:
- **Sound**: per-app volume, **choose the speaker for each app** (e.g. YouTube on the
  speakers, music on the headset), and a swipeable **Now Playing** carousel with
  every player and browser tab.
- **Quick settings**: battery and power mode, Wi-Fi, Bluetooth devices (with their
  battery), Do Not Disturb, stay awake, screen brightness (DDC/CI for external screens).
- **Clock**: click the bar clock (either button) for one popup with a calendar
  (Gregorian / Persian Solar Hijri, with weather) and up to 4 pinned timezones.
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
On other distros, install the packages yourself (see `packages.sh` for the list) and
run `./install.sh --configs-only`.

## Install

```sh
git clone https://github.com/<you>/gear5
cd gear5
./install.sh            # --dry-run shows what it would do
```

The installer:
1. installs the packages (asks for `sudo`), plus the JetBrainsMono Nerd Font if missing;
2. moves your current `~/.config/hypr`, `waybar` and `swaync` into
   `~/.config/gear5-backup-<date>/`;
3. copies the configs and downloads the wallpapers from the original rice.

Then log out and choose **Hyprland** on the login screen (GDM, SDDM, …).

To undo: delete `~/.config/{hypr,waybar,swaync}` and move the folders back out of the
backup.

If something stops working (a popup does not open, charge limits do nothing, a
Flatpak app will not start), run `./doctor.sh`. It checks the packages, the battery
udev rule, the user services and the document portal, and the popups, and prints the
command that fixes each problem. It changes nothing by itself.

## Make it yours

- **Theme and wallpaper**: `SUPER+I` → Theme / Wallpaper. From a terminal:
  `~/.config/waybar/scripts/theme.py list`, then `theme.py apply <name>`. The bar
  recolors in place (it restarts only if it was not already running); popups, borders,
  lock screen, wallpaper and kitty's colors all switch too; see
  `~/.config/hypr/themes/README.md` to make your own.
- **Theme GIF**: each theme can have a GIF of your own (8 MB or less, kept as
  `~/.config/hypr/themes/<theme id>.gif`, never in git). `SUPER+I` → Theme: *GIF…* on a
  card picks it and *Remove* deletes it. The GIF plays on the bar, left of the desks
  (click it to open the Theme page), and on the lock screen above the clock; a theme with no GIF
  has no pill on the bar and no picture on the lock screen. Neither
  Waybar nor hyprlock plays a GIF, so both show its frames one after the other
  (a flip-book). *Bar GIF plays* chooses when the bar moves: always, only on AC power
  (the default), or for 5 s after a theme switch; otherwise it rests on the first
  frame. The lock screen plays while it is locked. *GIF on theme switch* pops the GIF up
  under the bar for about two seconds when you switch theme. No picture ships with the project.
- **Fonts**: `SUPER+I` → Fonts. The English (mono) and the Persian font of the bar,
  popups, notifications, lock screen and kitty, chosen from the installed families
  and applied everywhere at once.
- **Everything else**: `SUPER+I` has a page for displays (with each screen's
  brightness, and a night light that follows sunset or a schedule), Wi-Fi, Bluetooth, sound, power & sleep (power mode, the sleep
  timer, and lock / sleep / reboot / power off), **Battery** (level, health,
  cycles, and charge limits, where the firmware's `charge_types` can be written —
  a `battery-limits` user service enforces
  them at login, every 30 s, and within 2 s of a change), notifications, keyboard &
  touchpad, and look & behavior (gaps, animations, the bar strip). Displays, Wi-Fi, Sound and the
  power page's panels are the same as the bar popups'. Bluetooth is the Bluetooth
  part of Quick settings. `settings.py <page>` opens a page directly (e.g.
  `settings.py wifi`). Your keyboard, touchpad and look choices are kept in
  `~/.config/hypr/user-settings.json` and win over `hyprland.lua`.
- **Zen Browser shows the same tabs in every window**: that is Zen's *Window Sync*
  (Zen 1.18+), not this desktop. To turn it off, open `about:config` and set
  `zen.window-sync.enabled` to `false` (tab renaming and dragging a tab into a new
  window then behave differently; see Zen's
  [Window Sync docs](https://docs.zen-browser.app/user-manual/window-sync)). For a single
  unsynced window, search *New Blank Window* in `SUPER+D`.
- **Monitors**: press `SUPER+P`. Layouts you keep are saved in
  `~/.config/hypr/displays.json`, one per set of connected screens. For fixed rules,
  see the *Monitors* section of `hyprland.lua`; `HOME_SLOTS` pins external screens to a
  desk block.
- **Vertical screens** get a compact bar with only the workspaces, automatically
  (`waybar/scripts/bar_config.py` reads which screens are rotated).
- **Bar logo**: detected from `/etc/os-release`; force one with
  `echo arch > ~/.config/waybar/distro`.
- **Brightness of external screens** uses DDC/CI: your user may need to be in the
  `i2c` group (`sudo usermod -aG i2c $USER`).

## Characters & wallpapers

Besides **Summer night**, there is a dark theme for each Straw Hat: the bar, popups,
notifications, window borders and lock screen take that character's colors.

| Theme id | Character | Colors |
|---|---|---|
| `luffy-gear5` | Luffy · Gear 5 (Sun God Nika) | cloud cream, Nika purple, sun yellow |
| `luffy` | Monkey D. Luffy | straw yellow, shorts blue, vest red |
| `zoro` | Roronoa Zoro | sword green, haramaki gold |
| `nami` | Nami | tangerine orange, sky blue |
| `usopp` | Usopp | sniper yellow, leaf green |
| `sanji` | Vinsmoke Sanji | blond gold, eyebrow blue, flame orange |
| `chopper` | Tony Tony Chopper | hat pink, nose blue, fur brown |
| `robin` | Nico Robin | lilac, flower pink |
| `franky` | Franky | cola cyan, star yellow |
| `brook` | Brook | bone white, soul gold, violet |
| `jinbe` | Jinbe | fish-man teal, kimono orange |

Switch with `~/.config/waybar/scripts/theme.py apply zoro` (list them with
`theme.py list`).

**No One Piece images come with this project, and none may be added to it.** One Piece,
its characters and its logos belong to Eiichiro Oda, Shueisha and Toei Animation, and
every fan wallpaper belongs to the artist who drew it. Credit or a link does not give
anyone the right to redistribute them. So each person adds their own:

1. Find a wallpaper you may use. Many fan-art sites mark each picture's terms; look
   for "free for personal use" and respect "contact the artist" for anything else.
   Example: [Luffy's Gear 5 by rickrickyy](https://wall.alphacoders.com/big.php?i=1325389)
   on Wallpaper Abyss is free for private, personal use.
2. Set it once from `SUPER+I` → Wallpaper → Choose…, or save it as
   `~/.config/hypr/wallpapers/wallpaper.png` (or `.jpg`, `.jpeg`, `.webp`). It is the
   same picture for every theme; with none, the desktop is filled with the current
   theme's background color.
3. For a GIF on the bar and the lock screen, pick one per theme from `SUPER+I` → Theme →
   *GIF…* on a card. The lock screen also shows the battery and what is playing.

To change a character's colors, edit `~/.config/hypr/themes/<theme id>.json` (the color
names are explained in `~/.config/hypr/themes/README.md`), then apply it again. To add
another character, copy one of the files under a new name.

## Credits

- [**summer-day-and-night**](https://github.com/MathisP75/summer-day-and-night) by
  **MathisP75** — the original rice: design, bar style, colors and wallpapers.
- [Everforest](https://github.com/sainnhe/everforest) color scheme by sainnhe.
- The character themes are fan color schemes inspired by *One Piece* by Eiichiro Oda
  (Shueisha / Toei Animation). No artwork is included; see *Characters & wallpapers*.
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
