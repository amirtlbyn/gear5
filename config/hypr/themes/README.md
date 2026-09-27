# Themes

One file per theme: `<id>.json`. Pick one with the Settings app, or run
`~/.config/waybar/scripts/theme.py apply <id>`. That writes the files below and
reloads Hyprland: the bar recolors in place (Hyprland restarts it only if it is
not already running), and the popups, notifications, window borders, the lock
screen and the wallpaper all switch too:

- `~/.config/hypr/themes/current` — the id of the theme in use
- `~/.config/hypr/themes/current.lua` — what `hyprland.lua` reads
- `~/.config/hypr/hyprlock-colors.conf` — lock screen colors and wallpaper
- `~/.config/waybar/colors/current.css` — bar and notification colors

Never edit those four by hand: the next switch writes them again.

## Colors

A theme only needs the colors that differ from `summer-night.json`; the rest come
from it. The names are roles, not hues: in a pink theme, `green` can be pink.

| Name | Used for |
|---|---|
| `bg_dim`, `bg0` … `bg5` | backgrounds, darkest to lightest (`bg0` = popups and bar boxes) |
| `fg`, `grey0`, `grey`, `grey2` | text, and dimmer text |
| `green` | main accent: launcher button, selected things, switches |
| `aqua`, `blue`, `purple`, `orange`, `yellow` | other accents (`blue` = active desk) |
| `red`, `red_hover` | power button, errors, close buttons |
| `on_accent` | text on an accent color |
| `edge`, `edge_deep` | the raised "3D" bottom edge of popups and bar boxes |
| `green_edge`, `red_edge`, `blue_edge` | that edge under a `green`, `red` or `blue` box |
| `bar_edge` | the bar's own bottom edge, and the window shadow |
| `shadow`, `shadow_inactive` | popup shadow; inactive window shadow |
| `bg_visual`, `bg_red`, `bg_green`, `bg_blue`, `bg_yellow` | tinted backgrounds |

## Wallpaper

One picture for every theme: `~/.config/hypr/wallpapers/wallpaper.png` (or `.jpg`,
`.jpeg`, `.webp`), set from Settings → Wallpaper. With no file, the desktop is filled
with the current theme's `bg0` color.
