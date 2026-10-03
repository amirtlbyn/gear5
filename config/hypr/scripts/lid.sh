#!/usr/bin/env bash
# Laptop lid: with an external screen connected, turn the laptop panel off
# and keep working; without one, systemd puts the laptop to sleep as usual.
# "check" reads the real lid state (for startup and monitor plug/unplug).
FLAG="${XDG_RUNTIME_DIR:-/tmp}/hypr-lid-closed"
external_count() { hyprctl monitors | awk '/^Monitor /{ if ($2 !~ /^(eDP|LVDS|DSI)/) n++ } END { print n+0 }'; }
case "$1" in
  close)
    internal=$(hyprctl monitors all | awk '/^Monitor (eDP|LVDS|DSI)/{print $2; exit}')
    if [[ -n "$internal" && ! -f "$FLAG" && $(external_count) -gt 0 ]]; then
      echo "$internal" > "$FLAG"
      hyprctl reload >/dev/null
    fi ;;
  open)
    # the layout file was written with the lid closed (panel off): write it again
    # before the reload reads it, or the panel stays off
    if [[ -f "$FLAG" ]]; then
      rm -f "$FLAG"
      ~/.config/waybar/scripts/displays.py --auto --lid-opened
      hyprctl reload >/dev/null
    fi ;;
  check)
    if grep -qs closed /proc/acpi/button/lid/*/state; then
      # lid closed and no external screen: they are asleep (lock, screen off) or
      # unplugged, and then the laptop suspends. Either way leave the panel off;
      # turning it on here would pile every window onto it.
      if [[ $(external_count) -gt 0 ]]; then "$0" close; fi
    else
      "$0" open
    fi ;;
esac
