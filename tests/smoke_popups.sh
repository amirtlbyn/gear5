#!/usr/bin/env bash
# Start every popup hidden for 3 s on a private D-Bus session (so it can't reach the
# popups you have running, and never shows or grabs the keyboard). A popup passes
# when it is still running at the end and printed no Python error.
#   tests/smoke_popups.sh [THEME]
cd "$(dirname "$0")/../config/waybar/scripts" || exit 1
theme="${1:-}"
fail=0
for p in volume-popup control-center wifi-menu calendar-popup power-popup calculator worldclock \
         emoji-picker clipboard launcher displays settings ${EXTRA_POPUPS:-}; do
  err=$(GTK_A11Y=none dbus-run-session -- timeout 3 ./"$p".py "$theme" --hidden 2>&1 >/dev/null)
  rc=$?
  if [[ $rc -ne 124 ]] || grep -q 'Traceback' <<<"$err"; then
    echo "FAIL $p (exit $rc)"; echo "$err" | tail -5; fail=1
  else
    echo "ok   $p"
  fi
done
# every Settings page, with the bar popups' panels inside it
err=$(GTK_A11Y=none dbus-run-session -- python3 ../../../tests/smoke_settings_pages.py 2>&1 >/dev/null)
rc=$?
if [[ $rc -ne 0 ]] || grep -q 'Traceback\|FAIL' <<<"$err"; then
  echo "FAIL settings pages (exit $rc)"; grep -A5 'Traceback\|FAIL' <<<"$err" | tail -8; fail=1
else
  echo "ok   settings pages"
fi
exit $fail
