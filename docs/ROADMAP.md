# Gear5 roadmap

The plan for the features and performance work that we agreed on 2026-09-27.
We do the items one at a time, in the order of this file. Each item goes
through the craft workflow (a spec, approval, the tests, a review) before the
next one starts.

Status: `todo` · `in progress` · `done` · `dropped`

## Where we start

Measured on the IdeaPad Slim 3 (Fedora 44, Hyprland 0.56), 2026-09-27:

| What | Value |
|---|---|
| Python in `config/waybar/scripts/` | 12,982 lines in 27 files, plus 1,764 lines of tests |
| RAM of the popup daemons (14 Python processes) | about 1.1 GB |
| RAM of one popup daemon while hidden | 60–150 MB |
| RAM of a minimal GTK4 window with no code of ours | 102 MB |
| RAM of a bare Python process | 9 MB |
| Picker open time (warm) | 99–108 ms |

Conclusion: GTK costs the most RAM in each process, and Python costs little. So the
number of processes controls the total RAM, and the language does not. That is why
phase 3 merges the popups into one process before it looks at Rust.

## Done in the session of 2026-09-27

- Settings: panels get `on_show` again (Displays had no screens, Wi-Fi and
  Bluetooth were slow). Panels are prefetched at startup. A theme pick keeps the
  scroll position. (spec SETFIX)
- Settings: Battery page with charge limits (stop at / start at, presets, charge
  speed), the `battery-limits` user service, and the udev rule. (spec BATPICK, session 1)
- Minimized-windows picker on SUPER+SHIFT+-, with thumbnails, number keys, a
  filter, and close. (spec BATPICK, session 2)
- The document portal starts again when its FUSE mount is removed
  (`config/systemd/user/xdg-document-portal.service.d/restart.conf`).
- No screen jump on a theme switch: displays.py writes the applied layout to
  `~/.config/hypr/displays-current.lua`, and hyprland.lua loads it after its own
  monitor lines. (spec PH0, 2026-09-28)

## Phase 0 — close what is open

Small items that the session left. Do them together, or with phase 1.

| # | Item | Done when | Status |
|---|---|---|---|
| 0.1 | Live check of the SETFIX fixes: Displays shows the screens; picking a theme while scrolled down keeps the scroll | The developer confirms it on screen | todo |
| 0.2 | Live check of the picker with real keys: number, Delete, typing, Esc | The developer confirms it on screen | todo |
| 0.3 | Check that the global blur puts no halo on floating GTK windows (Settings over a busy wallpaper) | No halo, or one fix | todo |
| 0.4 | Fix `tests/smoke_control_center.py`: `--hidden` makes GTK exit before the checks run, so it passes and checks nothing | A broken assertion makes it fail | done |
| 0.5 | Picker: release the thumbnail textures on close (it keeps 148 MB now) | RSS after a close is near the RSS after startup | done |
| 0.6 | udev rule: two direct `RUN` entries, with no `/bin/sh -c` | Rule reinstalled; `charge_types` still `root:wheel 0664` after a reboot | done (reinstall with sudo) |

## Phase 1 — tidy Settings (next)

Goal: every setting has one page in Settings. Quick settings stays a shortcut
that repeats the most used controls. This is normal.

| # | Item | Done when | Status |
|---|---|---|---|
| 1.1 | Battery page: the only battery card in Settings (%, state, health, cycles, W) and the charge limits | No other Settings page shows the battery level | todo |
| 1.2 | Power & sleep: remove the battery card; power mode (Saver / Balanced / Speed) becomes its own row above "When I'm away" | The page has power mode, "When I'm away", "After", "Now" | todo |
| 1.3 | Displays: a Brightness slider for the selected screen, below Rotation and Mirror; remove it from Power & sleep | Moving it changes the selected screen only | todo |
| 1.4 | Icon pass: each section title has the correct icon (for example, the battery section does not use the power icon) | Checked by eye on every page | todo |
| 1.5 | Take the Settings screenshots again (power, displays, battery) and the picker screenshot | `docs/SCREENSHOTS.md` shows the new pages, with no empty cards | todo |

Route: task. Quick settings does not change.

## Phase 2 — a quieter bar

Goal: the bar shows state, and it shows numbers only when they are important.

| # | Item | Done when | Status |
|---|---|---|---|
| 2.1 | Wi-Fi, volume, battery: an icon only in the normal state; the number on hover, and always when the battery is below 30 % or charging | The bar has no permanent percentages in the normal state | todo |
| 2.2 | Clock: the time only; the date (Gregorian and Jalali) on hover and in the calendar popup | The bar has no long date string | todo |
| 2.3 | Stay awake: a small coffee icon that shows only when it is on, not the "awake" text pill | No text pill | todo |
| 2.4 | Try the pills with no light strip behind them; keep the strip only if it looks better | The developer chooses from two screenshots | todo |

Route: task. The popups do not change.

## Phase 3 — performance

Goal: the popup RAM goes from about 1.1 GB to about 200 MB, and the popups
still open at once.

| # | Item | Done when | Status |
|---|---|---|---|
| 3.1 | One popup host: one Python process holds every popup as its own layer window. `popup.sh`, the keybinds, the bar and the tests do not change. Settings already loads the popups' panels, so a large part of the code is ready | The measured RSS of all popups is 250 MB or less; each popup opens in 150 ms or less; `tests/smoke_popups.sh` is green | todo |
| 3.2 | A crash in one popup does not stop the others; the host restarts after a crash (systemd user unit, `Restart=on-failure`) | Kill test: the other popups still open | todo |
| 3.3 | Measure again and write the numbers in this file | The table above has a "after 3.1" column | todo |
| 3.4 | **Decision gate: Rust or not.** Use the measured numbers from 3.3. If we choose Rust: port one part at a time behind the same `popup.sh` interface. Start with the always-running parts (`battery.py --serve`, the bar scripts), then the popups. The desktop keeps working after each step. The other choice is Quickshell (Qt/QML, one process by design), which is a full rewrite | A decision is written here, with its reason | todo |

Route: project (3.1 changes every popup). A Rust port (after 3.4) is one project
per part.

## Phase 4 — polish

| # | Item | Done when | Status |
|---|---|---|---|
| 4.1 | Motion: popups slide and fade from the bar (about 120 ms); picker cards scale in a little | It looks correct on a 60 Hz and a 100 Hz screen | todo |
| 4.2 | Lock screen: the theme's character art, the blurred wallpaper, battery and media status | It changes with the theme | todo |
| 4.3 | Notifications: an accent strip in the theme color; notifications grouped per app | Checked with three apps | todo |
| 4.4 | Empty states: Wi-Fi off, no Bluetooth devices, nothing minimized. Each shows one sentence and an action button | No blank lists | todo |

## Phase 5 — robustness

| # | Item | Done when | Status |
|---|---|---|---|
| 5.1 | A way out of a stuck overlay: SUPER+SHIFT+Escape stops any popup that holds the keyboard | Tested with a paused popup (SIGSTOP) | todo |
| 5.2 | `doctor.sh`: checks packages, the udev rule, the user services (battery-limits, the portals) and the popup daemons. It prints each problem and its fix | It finds each fault that we cause on purpose in a test | todo |
| 5.3 | Find what unmounts the document portal. The crash bursts of `xdg-desktop-portal-hyprland` come from the Claude Code process (reported with `/feedback`). The restart drop-in is only the workaround | The cause is known, or it is fixed upstream | todo |

## Phase 6 — bigger features

| # | Item | Done when | Status |
|---|---|---|---|
| 6.1 | Overview on SUPER+Tab: every desk and window as thumbnails. It uses the picker's capture code | It opens in 150 ms or less with 20 windows | todo |
| 6.2 | A "character moment" for each theme: a small animated sticker or bar accent that changes with the theme | Each built-in theme has one | todo |
| 6.3 | Night light: warmer colors at night, in the Displays page | It follows sunset, or a schedule | todo |
| 6.4 | Auto-dim when idle on battery, in the Battery page | The screen dims after N minutes, on battery only | todo |

## Rules for every item

- Start with `/craft`. The route comes from the workflow, not from this file.
- Measure before and after each performance item, and write the numbers here.
- Nothing is done until its tests pass and the review is green.
- When an item is done, change its status here in the same change.
