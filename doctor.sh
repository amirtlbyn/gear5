#!/usr/bin/env bash
# Gear5 doctor: checks the parts of the install that can break on their own
# (packages, the battery udev rule, the user services, the document portal's
# mount, the popup daemons) and prints each problem with the command that fixes
# it. It only reads: it changes nothing, and it needs no sudo.
#
#   ./doctor.sh        exit 0 when everything is fine, 1 when it found a problem
#
# The paths below come from the environment when set, so the tests can use fakes.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS_RELEASE="${OS_RELEASE:-/etc/os-release}"
UDEV_RULES_DIR="${UDEV_RULES_DIR:-/etc/udev/rules.d}"
POWER_SUPPLY="${POWER_SUPPLY:-/sys/class/power_supply}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
POPUPS="$HOME/.config/waybar/scripts"          # the folder popup.sh starts them from
DOC="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/doc"
. "$HERE/packages.sh"

problems=0
ok()      { printf 'ok    %s\n' "$1"; }
skip()    { printf 'skip  %s\n' "$1"; }
problem() { printf 'FAIL  %s\n      fix: %s\n' "$1" "$2"; problems=$((problems + 1)); }

check_packages() {
  local family pkgs=() missing=() p fix
  family=$(. "$OS_RELEASE" 2>/dev/null
           case " ${ID:-} ${ID_LIKE:-} " in
             *" fedora "*) echo fedora ;; *" arch "*) echo arch ;; *" ubuntu "*) echo ubuntu ;;
           esac)
  case "$family" in
    fedora) pkgs=("${FEDORA_PKGS[@]}"); fix="sudo dnf install" ;;
    arch)   pkgs=("${ARCH_PKGS[@]}");   fix="sudo pacman -S --needed" ;;
    ubuntu) pkgs=("${UBUNTU_PKGS[@]}"); fix="sudo apt-get install" ;;
    *) skip "packages: this is not Fedora, Arch or Ubuntu"; return ;;
  esac
  for p in "${pkgs[@]}"; do
    case "$family" in
      fedora) rpm -q "$p" >/dev/null 2>&1 ;;
      arch)   pacman -Q "$p" >/dev/null 2>&1 ;;
      ubuntu) [[ $(dpkg-query -W -f='${Status}' "$p" 2>/dev/null) == *"ok installed" ]] ;;
    esac || missing+=("$p")
  done
  if ((${#missing[@]})); then
    problem "packages not installed: ${missing[*]}" "$fix ${missing[*]}"
  else
    ok "packages (${#pkgs[@]}, $family)"
  fi
}

check_udev_rule() {
  local ct rule="$UDEV_RULES_DIR/90-summer-battery.rules" src="$HERE/config/udev/90-summer-battery.rules"
  ct=$(compgen -G "$POWER_SUPPLY/BAT*/charge_types" | head -1)
  if [[ -z "$ct" ]]; then
    skip "battery udev rule: this battery has no charge_types"
    return
  fi
  local apply="sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=power_supply --action=change"
  if [[ ! -e "$rule" ]]; then
    problem "the battery udev rule is not installed ($rule)" "sudo install -m644 $src $UDEV_RULES_DIR/ && $apply"
  elif ! cmp -s "$rule" "$src"; then
    problem "the battery udev rule differs from the one in $HERE" "sudo install -m644 $src $UDEV_RULES_DIR/ && $apply"
  else
    ok "battery udev rule"
  fi
  if [[ -w "$ct" ]]; then
    ok "battery charge type is writable"
  elif [[ $(stat -c %G "$ct") == wheel && " $(id -nG) " != *" wheel "* ]]; then
    problem "$ct belongs to the wheel group, and you are not in it" "sudo usermod -aG wheel $USER, then log out and in"
  else
    problem "$ct is not writable: the udev rule has not run on it" "$apply"
  fi
}

check_service() {   # unit, what it does
  if [[ $(systemctl --user is-active "$1" 2>/dev/null) == active ]]; then
    ok "$1"
  else
    problem "$1 is not running ($2)" "systemctl --user restart $1"
  fi
}

check_services() {
  if [[ $(systemctl --user is-enabled battery-limits.service 2>/dev/null) != enabled ||
        $(systemctl --user is-active battery-limits.service 2>/dev/null) != active ]]; then
    problem "battery-limits.service is not enabled and running (charge limits)" \
      "systemctl --user enable --now battery-limits.service"
  else
    ok "battery-limits.service"
  fi
  if [[ $(systemctl --user is-enabled night-light.service 2>/dev/null) != enabled ||
        $(systemctl --user is-active night-light.service 2>/dev/null) != active ]]; then
    problem "night-light.service is not enabled and running (Settings > Displays > Night light)" \
      "systemctl --user enable --now night-light.service"
  else
    ok "night-light.service"
  fi
  if [[ $(systemctl --user is-enabled bar-gif.service 2>/dev/null) != enabled ||
        $(systemctl --user is-active bar-gif.service 2>/dev/null) != active ]]; then
    problem "bar-gif.service is not enabled and running (the theme's GIF on the bar)" \
      "systemctl --user enable --now bar-gif.service"
  else
    ok "bar-gif.service"
  fi
  check_service xdg-desktop-portal.service "file pickers, screen sharing"
  check_service xdg-desktop-portal-hyprland.service "screen sharing, screenshots for apps"
  check_service xdg-document-portal.service "files for Flatpak apps"
  local dropin="$CONFIG/systemd/user/xdg-document-portal.service.d/restart.conf"
  if [[ -e "$dropin" ]]; then
    ok "document portal restart drop-in"
  else
    problem "the document portal restart drop-in is not installed ($dropin)" \
      "mkdir -p ${dropin%/*} && cp $HERE/config/systemd/user/xdg-document-portal.service.d/restart.conf ${dropin%/*}/ && systemctl --user daemon-reload"
  fi
}

check_doc_mount() {
  # the service can stay "active" after its mount is gone: Flatpak apps then fail
  # to start ("Can't find source path .../doc/by-app/...")
  if [[ $(systemctl --user is-active xdg-document-portal.service 2>/dev/null) != active ]]; then
    return   # check_services already reported it
  fi
  if [[ $(findmnt -n -o FSTYPE "$DOC" 2>/dev/null) == fuse.portal ]]; then
    ok "document portal mount ($DOC)"
  else
    problem "the document portal runs, but $DOC is not mounted" "systemctl --user restart xdg-document-portal.service"
  fi
}

check_popups() {
  if [[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
    skip "popups: not in a Hyprland session"
    return
  fi
  local all p pid bad=()
  all=$(sed -n 's/^all="\(.*\)"$/\1/p' "$POPUPS/popup.sh" 2>/dev/null)
  if [[ -z "$all" ]]; then
    problem "$POPUPS/popup.sh is missing: the configs are not installed" "./install.sh --configs-only"
    return
  fi
  for p in $all; do
    pid=$(pgrep -f -- "$POPUPS/$p\.py( |$)" | head -1)
    if [[ -z "$pid" ]]; then
      bad+=("$p")
    elif [[ $(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null) == [Tt] ]]; then
      bad+=("$p (paused)")
    fi
  done
  if ((${#bad[@]})); then
    local list
    printf -v list '%s, ' "${bad[@]}"
    problem "popups not running: ${list%, }" "~/.config/waybar/scripts/popup.sh --restart"
  else
    ok "popups ($(wc -w <<<"$all") running)"
  fi
}

check_packages
check_udev_rule
check_services
check_doc_mount
check_popups
echo
if ((problems)); then
  echo "$problems problem(s) found."
  exit 1
fi
echo "Everything looks fine."
