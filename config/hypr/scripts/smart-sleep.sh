#!/usr/bin/env bash
# Called by hypridle when you've been away long enough.
# Sleeps only if the computer is also quiet; otherwise checks again every minute.
# Any key/mouse activity stops this script (hypridle's on-resume kills it).
#
# "Busy" means any of:
CPU_BUSY=20          # % CPU in use (builds, updates, rendering…)
NET_BUSY=100         # KB/s network traffic (downloads, uploads, streaming)
DISK_BUSY=2048       # KB/s disk reading/writing (copying files…)
SAMPLE=5             # seconds to measure

cpu()  { awk '/^cpu /{print $2+$3+$4+$6+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }
net()  { awk -F'[: ]+' 'NR>2 && $2!="lo"{s+=$3+$11} END{print s+0}' /proc/net/dev; }
disk() { awk '$3 ~ /^(sd[a-z]+|nvme[0-9]+n[0-9]+|vd[a-z]+|mmcblk[0-9]+)$/{s+=$6+$10} END{print s+0}' /proc/diskstats; }

why_busy() {
  if pactl list sinks 2>/dev/null | grep -q "State: RUNNING"; then echo "sound is playing"; return; fi
  if systemd-inhibit --list --no-legend 2>/dev/null | awk '$NF=="block" && $6 ~ /sleep|idle/ {f=1} END{exit !f}'; then
    echo "an app asked to stay awake"; return; fi
  read -r cb1 ct1 < <(cpu); n1=$(net); d1=$(disk)
  sleep "$SAMPLE"
  read -r cb2 ct2 < <(cpu); n2=$(net); d2=$(disk)
  local cpu_pct=$(( (cb2 - cb1) * 100 / ( (ct2 - ct1) > 0 ? (ct2 - ct1) : 1 ) ))
  local net_kbs=$(( (n2 - n1) / 1024 / SAMPLE ))
  local disk_kbs=$(( (d2 - d1) / 2 / SAMPLE ))          # sectors are 512 bytes
  (( cpu_pct  >= CPU_BUSY  )) && { echo "CPU busy (${cpu_pct}%)"; return; }
  (( net_kbs  >= NET_BUSY  )) && { echo "network busy (${net_kbs} KB/s)"; return; }
  (( disk_kbs >= DISK_BUSY )) && { echo "disk busy (${disk_kbs} KB/s)"; return; }
}

notified=0
while :; do
  reason=$(why_busy)
  if [[ -z "$reason" ]]; then
    systemctl suspend
    exit 0
  fi
  if (( ! notified )); then
    notify-send -a "Power" -u low "Not sleeping yet" "Waiting because $reason"
    notified=1
  fi
  sleep 60
done
