#!/usr/bin/env bash
# The pop-up sticker on a private D-Bus session (see smoke_popups.sh for why): its
# window has keyboard mode none and an empty input region, and it exits by itself
# within 4 s, once with the theme's GIF and once without (spec CHAR-7).
#   tests/smoke_sticker.sh [THEME]
here="$(cd "$(dirname "$0")" && pwd)"
bus_conf="$here/private-bus.conf"
theme="${1:-zoro}"
scripts="$here/../config/waybar/scripts"
fail=0
err=$(GTK_A11Y=none dbus-run-session --config-file="$bus_conf" -- python3 "$here/smoke_sticker.py" 2>&1 >/dev/null)
if [[ $? -ne 0 ]] || grep -q 'Traceback\|FAIL' <<<"$err"; then
  echo "FAIL window rules"; echo "$err" | tail -5; fail=1
else
  echo "ok   keyboard mode none, empty input region"
fi
# a 1-pixel GIF in a scratch config folder, so the run does not touch the real one
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/hypr/characters" "$work/hypr/themes"
cp "$here/../config/hypr/themes/"*.json "$work/hypr/themes/"
printf 'GIF89a\001\000\001\000\200\000\000\000\000\000\377\377\377!\371\004\001\000\000\000\000,\000\000\000\000\001\000\001\000\000\002\002D\001\000;' \
  >"$work/hypr/characters/$theme.sticker.gif"
for variant in without with; do
  if [[ $variant == without ]]; then cfg="$work/none"; mkdir -p "$cfg/hypr"; cp -r "$work/hypr/themes" "$cfg/hypr/"; else cfg="$work"; fi
  start=$SECONDS
  err=$(XDG_CONFIG_HOME="$cfg" GTK_A11Y=none dbus-run-session --config-file="$bus_conf" -- timeout 4 "$scripts/sticker.py" "$theme" 2>&1 >/dev/null)
  rc=$?
  if [[ $rc -ne 0 ]] || grep -q 'Traceback' <<<"$err"; then
    echo "FAIL sticker $variant GIF (exit $rc after $((SECONDS - start)) s)"; echo "$err" | tail -5; fail=1
  else
    echo "ok   sticker $variant GIF exits by itself ($((SECONDS - start)) s)"
  fi
done
exit $fail
