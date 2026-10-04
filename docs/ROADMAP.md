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
| 0.1 | Live check of the SETFIX fixes: Displays shows the screens; picking a theme while scrolled down keeps the scroll | The developer confirms it on screen | done (confirmed by the developer 2026-10-04) |
| 0.2 | Live check of the picker with real keys: number, Delete, typing, Esc | The developer confirms it on screen | done (confirmed by the developer 2026-10-04) |
| 0.3 | Check that the global blur puts no halo on floating GTK windows (Settings over a busy wallpaper) | No halo, or one fix | done (2026-10-04: Settings floating over a browser page, grim before and after; outside the 4 px border the pixels do not change (2.6 % at every distance from 5 to 30 px, which is the page behind, not a halo) and the text next to the border stays sharp. No window has an opacity below 1, so blur never applies) |
| 0.4 | Fix `tests/smoke_control_center.py`: `--hidden` makes GTK exit before the checks run, so it passes and checks nothing | A broken assertion makes it fail | done |
| 0.5 | Picker: release the thumbnail textures on close (it keeps 148 MB now) | RSS after a close is near the RSS after startup | done |
| 0.6 | udev rule: two direct `RUN` entries, with no `/bin/sh -c` | Rule reinstalled; `charge_types` still `root:wheel 0664` after a reboot | done (reinstall with sudo) |

## Phase 1 — tidy Settings (next)

Goal: every setting has one page in Settings. Quick settings stays a shortcut
that repeats the most used controls. This is normal.

| # | Item | Done when | Status |
|---|---|---|---|
| 1.1 | Battery page: the only battery card in Settings (%, state, health, cycles, W) and the charge limits | No other Settings page shows the battery level | done |
| 1.2 | Power & sleep: remove the battery card; power mode (Saver / Balanced / Speed) becomes its own row above "When I'm away" | The page has power mode, "When I'm away", "After", "Now" | done |
| 1.3 | Displays: a Brightness slider for the selected screen, below Rotation and Mirror; remove it from Power & sleep | Moving it changes the selected screen only | done |
| 1.4 | Icon pass: each section title has the correct icon (for example, the battery section does not use the power icon) | Checked by eye on every page | done (eye pass pending) |
| 1.5 | Take the Settings screenshots again (power, displays, battery) and the picker screenshot | `docs/SCREENSHOTS.md` shows the new pages, with no empty cards | done (blur before publishing) |

Route: task. Quick settings does not change.

## Phase 2 — a quieter bar

Goal: the bar shows state, and it shows numbers only when they are important.

| # | Item | Done when | Status |
|---|---|---|---|
| 2.1 | Wi-Fi, volume, battery: an icon only in the normal state; the number on hover, and always when the battery is below 30 % or charging | The bar has no permanent percentages in the normal state | done |
| 2.2 | Clock: the time only; the date (Gregorian and Jalali) on hover and in the calendar popup | The bar has no long date string | done |
| 2.3 | Away-timer pill: only the mode glyph (sleep, lock, or a coffee cup for stay awake), the minutes on hover, on the left side after the clock. Volume, battery and this pill are the same size as the network pill, with the glyph centered. It stays in every mode, so one click changes the mode | No text pill (spec AWAKE) | done |
| 2.4 | Try the pills with no light strip behind them; keep the strip only if it looks better. The developer chose a switch: Settings > Look & behavior > Bar background (on by default) | The developer chooses from two screenshots (spec STRIP) | done |

Route: task. The popups do not change.

## Phase 3 — performance

Goal: the popup RAM goes from about 1.1 GB to about 200 MB, and the popups
still open at once.

| # | Item | Done when | Status |
|---|---|---|---|
| 3.1 | One popup host: one Python process holds every popup as its own layer window. `popup.sh`, the keybinds, the bar and the tests do not change. Settings already loads the popups' panels, so a large part of the code is ready | The measured RSS of all popups is 250 MB or less; each popup opens in 150 ms or less; `tests/smoke_popups.sh` is green | dropped (2026-09-29: one host saves about 150 MB of real RAM, not 900 MB; see the measurements below) |
| 3.2 | A crash in one popup does not stop the others; the host restarts after a crash (systemd user unit, `Restart=on-failure`) | Kill test: the other popups still open | dropped (it only applies to a single host) |
| 3.3 | Measure again and write the numbers in this file | The table above has a "after 3.1" column | done (the "Measured 2026-09-29" table below) |
| 3.4 | **Decision gate: Rust or not.** Use the measured numbers from 3.3. If we choose Rust: port one part at a time behind the same `popup.sh` interface. Start with the always-running parts (`battery.py --serve`, the bar scripts), then the popups. The desktop keeps working after each step. The other choice is Quickshell (Qt/QML, one process by design), which is a full rewrite | A decision is written here, with its reason | done (2026-09-29: no Rust; see "Decision 3.4" below) |

Route: project (3.1 changes every popup). A Rust port (after 3.4) is one project
per part.

### Measured 2026-09-29, before 3.1 (spec LEAK)

The 11 popups, each opened once (warm). RSS counts the shared GTK libraries once
per process; PSS shares them out, so PSS is the RAM they really use.

| What | Before LEAK | After LEAK |
|---|---|---|
| RSS of the 11 popups | 1310 MB | 1263 MB |
| PSS of the 11 popups | 488 MB | 475 MB |
| Clipboard, growth per open (12 pictures in the history) | +17.6 MB, no limit | +0.2 MB |
| Minimized picker, growth per open (1 window) | +5.2 MB, no limit | 0 MB |
| The other 9 popups, growth per open | 0 | 0 |
| A popup whose script was removed (calendar-popup) | kept running (120 MB RSS) | stopped by `popup.sh --restart` |
| Open time, median of 3 warm opens (Hyprland `openlayer` event) | 88–229 ms | not changed |

Estimate for 3.1: one bare GTK4 process is 105 MB RSS (28 MB private), and the
popups' own memory is about 228 MB, so one host would be about 330 MB RSS. That
saves about 150 MB of real RAM (PSS 475 → about 330). The 250 MB target is out
of reach without also making each popup smaller. Six popups already open in more
than 150 ms.

### Decision 3.4, 2026-09-29: no Rust

We stay on Python and GTK4. We do not port to Rust, and we do not move to
Quickshell.

Measured on 2026-09-29, 34 minutes after `popup.sh --restart`, with the popups hidden:

| What | Value |
|---|---|
| PSS of the 11 popups | 340 MB (22–46 MB each) |
| The same, as a part of the RAM (39.7 GB) | 0.85 % |
| `battery.py --serve` | 5 MB PSS; 6 s of CPU in 22 hours |
| `clock.sh`, `lang.sh` (bash) | less than 1 MB PSS together |
| Python start with the GTK4 and layer-shell imports | 0.13 s, 55 MB peak |

Reasons:

- GTK4 costs the most, and a Rust program also loads GTK4 (gtk4-rs). A bare
  GTK4 process is 105 MB RSS and 28 MB private in any language. A port removes
  only the Python part: about 10–15 MB per popup, about 110–160 MB in total.
  That is not enough to justify a rewrite of 13,800 lines.
- The always-running parts, where the roadmap said to start, use about 5 MB and
  almost no CPU. A port of them saves nothing that we can measure.
- Quickshell is one process, but it is a full rewrite of the bar, the popups,
  and Settings, and waybar and swaync go too. We did not measure its RAM.
- The slow popup opens (88–229 ms) do not come from the Python start: the
  popups are already running when they open.

We look at this again when one of these is true: Gear5 must run on a machine
with 8 GB of RAM or less; a profile shows that Python code, not GTK, makes a
popup open in more than 150 ms; or the popup count grows so much that the RAM
becomes a problem.

## Phase 4 — polish

| # | Item | Done when | Status |
|---|---|---|---|
| 4.1 | Motion: popups slide and fade from the bar (about 120 ms); picker cards scale in a little | It looks correct on a 60 Hz and a 100 Hz screen (spec MOTION) | done (checked with grim at 100 Hz; eye check done 2026-10-04) |
| 4.2 | Lock screen: the theme's character art, the blurred wallpaper, battery and media status. The pictures are each person's own, one per theme, from Settings > Lock screen | It changes with the theme (spec LOCK) | done (eye check on a real lock done 2026-10-04) |
| 4.3 | Notifications: an accent strip in the theme color; notifications grouped per app (in the notification center: swaync does not group pop-ups) | Checked with three apps (spec NOTIF) | done |
| 4.4 | Empty states: Wi-Fi off, no Bluetooth devices, nothing minimized. Each shows one sentence and an action button | No blank lists (spec EMPTY) | done |

## Phase 5 — robustness

| # | Item | Done when | Status |
|---|---|---|---|
| 5.1 | A way out of a stuck overlay: SUPER+SHIFT+Escape stops any popup that holds the keyboard | Tested with a paused popup (SIGSTOP) | done (spec UNSTICK: `popup.sh --unstick`, `tests/live_unstick.sh`; key press check pending) |
| 5.2 | `doctor.sh`: checks packages, the udev rule, the user services (battery-limits, the portals) and the popup daemons. It prints each problem and its fix | It finds each fault that we cause on purpose in a test | done (spec DOCTOR; its first live run found the old udev rule of 0.6) |
| 5.3 | Find what unmounts the document portal. The crash bursts of `xdg-desktop-portal-hyprland` come from the Claude Code process (reported with `/feedback`). The restart drop-in is only the workaround | The cause is known, or it is fixed upstream | done (spec PORTAL: our smoke tests did it; see "Finding 5.3" below) |

### Finding 5.3, 2026-09-29: our smoke tests unmounted the document portal

`/run/user/1000/doc` was unmounted 939 times between 2026-09-26 and 2026-09-29, in
bursts of one every 6–8 s. Each unmount came in the same second as a segfault of a
second `xdg-desktop-portal-hyprland` in `libwayland-client`. The bursts matched
the runs of `tests/smoke_popups.sh`.

The cause: the smoke tests started each popup under `dbus-run-session`, with the
default session config. GTK asks the private bus for the settings portal, so that
bus started its own `xdg-desktop-portal`. That portal started a second
`xdg-document-portal`, which took over `/run/user/1000/doc`. The real one exited
with status 21, or once stayed up with no mount. When the private bus closed, the
second portal unmounted the folder and the second `xdg-desktop-portal-hyprland`
segfaulted. The processes ran in the terminal's scope, where Claude Code ran the
tests, so the earlier `/feedback` report blamed Claude Code by mistake. Flatpak
apps (Telegram, Spotify) then failed with "Can't find source path
/run/user/1000/doc/by-app/…", and two restarts of the portal on 2026-09-29 came
from that.

The fix: the smoke tests use `tests/private-bus.conf`, a bus config with no service
folder, so the private bus starts nothing. After the fix, a full smoke run keeps
the same mount ID and writes no unmount or segfault line to the journal. The
restart drop-in stays, because other tools can start a private bus too.
`doctor.sh` now finds a portal that runs with no mount.

## Phase 6 — bigger features

| # | Item | Done when | Status |
|---|---|---|---|
| 6.1 | Overview on SUPER+Tab: every desk and window as thumbnails. It uses the picker's capture code | It opens in 150 ms or less with 20 windows | done (spec OVERVIEW: median 68–85 ms with 20 windows, `tests/live_overview.py`; 20 thumbnails 190–210 ms after; group next moved to SUPER+SHIFT+G) |
| 6.2 | A "character moment" for each theme: a small animated sticker or bar accent that changes with the theme | Each built-in theme has one | done (spec CHARACTER-MOMENT: a glyph sticker on the bar (spec GIF: the bar now plays the theme's GIF instead, and no pill without one) and a pop-up at each switch, per-theme glyph, motion and GIF in Settings > Stickers; the eye check of the motions on both screens is done). Note (spec GIFT-ONLY, 2026-10-03): the glyph and the motion are gone. The GIF is the only character, kept as `themes/<id>.gif`, and it is set on the Theme page; eye check of the Theme page GIF and a real GIF lock done 2026-10-04 |
| 6.3 | Night light: warmer colors at night, in the Displays page | It follows sunset, or a schedule | done (spec NIGHT: wlsunset through the night-light user service; Off, Follow sunset (the calendar's home city, offline) or Schedule, 2500–5500 K; eye check done 2026-10-04) |
| 6.4 | Auto-dim when idle on battery, in the Battery page | The screen dims after N minutes, on battery only | done (spec BDIM: Settings > Battery > Dim when idle, Off or 1–10 min, to 30 %; activity brings back the brightness from before the first dim; Off by default; eye check done 2026-10-04) |
| 6.5 | Lock screen GIF: first find out what hyprlock's image widget does with a GIF (plays it, shows the first frame, or shows nothing). If it can play one, Settings > Lock screen accepts a GIF per theme, like Settings > Stickers | The hyprlock result is written here; then either the Lock screen page takes a GIF, or the reason it cannot | done (spec GIF: hyprlock plays no GIF itself; it plays the GIF as a flip-book driven by SIGUSR2 on an image with `reload_time = 0`. The GIF is added in Settings > Stickers, not on the Lock screen page, and wins over the theme's picture; the eye check of a real lock is done (2026-10-04)). Note (spec GIFT-ONLY, 2026-10-03): the GIF is now set on the Theme page, there is no Lock screen page, and a theme with no GIF shows no lock picture |
| 6.6 | Shortcuts page in Settings: change or turn off any desktop shortcut | A new key press is saved and applied at once; taken keys are refused | done (spec KEYS: `shortcut(...)` names in `hyprland.lua`, keys kept in user-settings.json, Settings > Shortcuts records a key press with the shortcuts inhibitor; eye check pending) |

## Rules for every item

- Start with `/craft`. The route comes from the workflow, not from this file.
- Measure before and after each performance item, and write the numbers here.
- Nothing is done until its tests pass and the review is green.
- When an item is done, change its status here in the same change.
