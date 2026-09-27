#!/usr/bin/env bash
# LIVE SESSION ONLY (needs a running Hyprland, Waybar and swaybg). A theme switch
# recolors the bar and keeps the wallpaper on screen instead of restarting them,
# and the bar is still there afterwards: GEAR-5, GEAR-6, GEAR-7, GEAR-8.
#   tests/smoke_theme_switch.sh [THEME]   (default: zoro; switches back when done)
set -u
THEME_PY=~/.config/waybar/scripts/theme.py
CSS=~/.config/waybar/colors/current.css
target="${1:-zoro}"
before="$("$THEME_PY" current)"
fail=0

echo "checking GEAR-5, GEAR-6, GEAR-7, GEAR-8 (theme in use: $before, switching to: $target)"

waybar_before=$(pgrep -x waybar | sort)
swaybg_before=$(pgrep -x swaybg | sort)
css_before=$(md5sum "$CSS" 2>/dev/null)
# a strip of the bar on the focused screen: it must look different after the switch
shot() { grim -g "$(hyprctl -j monitors | jq -r '.[] | select(.focused) | "\(.x),\(.y) \(.width)x40"')" - | md5sum; }
bar_before=$(shot)

"$THEME_PY" apply "$target" >/dev/null
sleep 2

waybar_after=$(pgrep -x waybar | sort)
swaybg_after=$(pgrep -x swaybg | sort)
css_after=$(md5sum "$CSS" 2>/dev/null)
bar_after=$(shot)

[[ -n "$waybar_after" ]] || { echo "FAIL no waybar running after the switch (GEAR-8)"; fail=1; }
[[ "$waybar_before" == "$waybar_after" ]] || {
  echo "FAIL waybar restarted: pid(s) [$waybar_before] -> [$waybar_after] (GEAR-5)"; fail=1; }
[[ "$swaybg_before" == "$swaybg_after" ]] || {
  echo "FAIL swaybg restarted: pid(s) [$swaybg_before] -> [$swaybg_after] (GEAR-6)"; fail=1; }
[[ "$css_before" != "$css_after" ]] || { echo "FAIL colors file did not change (GEAR-7)"; fail=1; }
[[ "$bar_before" != "$bar_after" ]] || { echo "FAIL the bar on screen did not change color (GEAR-5)"; fail=1; }

# back to the theme this ran on
"$THEME_PY" apply "$before" >/dev/null
sleep 2
[[ -n "$(pgrep -x waybar)" ]] || { echo "FAIL no waybar running after switching back (GEAR-8)"; fail=1; }

[[ $fail -eq 0 ]] && echo "ok   theme switch is smooth (waybar and swaybg kept their PIDs, the bar changed color)"
exit $fail
