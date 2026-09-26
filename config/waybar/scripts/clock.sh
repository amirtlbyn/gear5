#!/usr/bin/env bash
# Bar clock with pinned timezones (edit them in the world clock popup: click the clock).
#   clock.sh            keep printing the clock for waybar (only when it changes)
#   clock.sh next|prev  show the next / previous pinned zone on the bar (mouse wheel)
STATE=~/.config/waybar/clock-zones.json
LOCAL=$(readlink -f /etc/localtime | sed 's|.*/zoneinfo/||')

city() {  # Asia/Tehran → Tehran, America/New_York → New York
  local z=$1; [[ $z == local ]] && z=$LOCAL
  z=${z##*/}; echo "${z//_/ }"
}

# short name for the bar: Tehran → TEH, New York → NY, or your own from "labels"
# in clock-zones.json, e.g. "labels": {"Asia/Tehran": "IR"}
short() {
  local custom c out=""
  custom=$(jq -r --arg z "$1" '.labels[$z] // empty' "$STATE" 2>/dev/null)
  if [[ -n $custom ]]; then echo "$custom"; return; fi
  c=$(city "$1")
  if [[ $c == *" "* ]]; then
    for w in $c; do out+=${w:0:1}; done
  else
    out=${c:0:3}
  fi
  echo "${out^^}"
}

if [[ "$1" == next || "$1" == prev ]]; then
  step=1; [[ "$1" == prev ]] && step=-1
  tmp=$(mktemp)
  jq --argjson s "$step" '(.active // "local") as $a | .pinned as $p | (($p | index($a)) // 0) as $i
      | .active = $p[(($i + $s) % ($p | length) + ($p | length)) % ($p | length)]' "$STATE" > "$tmp" \
    && mv "$tmp" "$STATE"
  exit
fi

emit() {
  local active zone text tip=""
  active=$(jq -r '.active // "local"' "$STATE" 2>/dev/null || echo local)
  zone=$active; [[ $zone == local ]] && zone=$LOCAL
  text=" $(TZ=$zone date +%H:%M) $(short "$active")"
  while read -r z; do
    local tz=$z; [[ $tz == local ]] && tz=$LOCAL
    tip+=$(printf '%-14s %s' "$(city "$z")" "$(TZ=$tz date '+%H:%M  %a')")$'\n'
  done < <(jq -r '.pinned[]' "$STATE" 2>/dev/null)
  jq -cn --arg t "$text" --arg tip "${tip%$'\n'}" --arg c "$([[ $active == local ]] && echo local || echo other)" \
    '{text: $t, tooltip: $tip, class: $c}'
}

last=""
while :; do
  key="$(date +%H:%M)$(stat -c %Y "$STATE" 2>/dev/null)"
  if [[ "$key" != "$last" ]]; then emit; last=$key; fi
  sleep 1
done
