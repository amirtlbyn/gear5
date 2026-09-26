#!/usr/bin/env bash
# Summer Hyprland installer — Fedora 44+, Arch (and Arch-based), Ubuntu / Kubuntu 26.04+.
#
#   ./install.sh                 install packages + fonts + configs (asks before changing anything)
#   ./install.sh --yes           don't ask
#   ./install.sh --configs-only  only copy the configs (you install the packages yourself)
#   ./install.sh --theme day     start with the light theme (default: night)
#   ./install.sh --dry-run       show what would happen, change nothing
#
# Your current ~/.config/{hypr,waybar,swaync} are moved to a dated backup folder first.
set -euo pipefail

UPSTREAM="https://github.com/MathisP75/summer-day-and-night"   # original rice: wallpapers + kitty colors
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
FONTS="${XDG_DATA_HOME:-$HOME/.local/share}/fonts"

YES=0 DRY=0 PACKAGES=1 THEME=night
while (($#)); do
  case "$1" in
    -y|--yes) YES=1 ;;
    --dry-run) DRY=1 ;;
    --configs-only) PACKAGES=0 ;;
    --theme) THEME="${2:-night}"; shift ;;
    -h|--help) sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1 (see --help)" >&2; exit 1 ;;
  esac
  shift
done
[[ "$THEME" == day || "$THEME" == night ]] || { echo "--theme is day or night" >&2; exit 1; }

say()  { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if ((DRY)); then printf '   [dry-run] %s\n' "$*"; else "$@"; fi; }
ask()  { ((YES || DRY)) && return 0; read -r -p "$1 [Y/n] " a; [[ -z "$a" || "$a" =~ ^[Yy] ]]; }

# ---------------------------------------------------------------- which Linux
[[ -r /etc/os-release ]] || die "Can't tell which Linux this is (no /etc/os-release)."
. /etc/os-release
FAMILY=""
case " $ID ${ID_LIKE:-} " in
  *" fedora "*) FAMILY=fedora ;;
  *" arch "*)   FAMILY=arch ;;
  *" ubuntu "*) FAMILY=ubuntu ;;
esac
NAME_SHOWN="${PRETTY_NAME:-$ID}"
if [[ "$FAMILY" == ubuntu ]] && { [[ -d /usr/share/kubuntu-default-settings ]] ||
     dpkg-query -W -f='${Status}' kubuntu-desktop 2>/dev/null | grep 'ok installed' >/dev/null; }; then
  NAME_SHOWN="Kubuntu ${VERSION_ID:-}"
fi
[[ -n "$FAMILY" ]] || die "$NAME_SHOWN isn't supported yet (Fedora, Arch, Ubuntu and Kubuntu are). Try --configs-only."

version_ge() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }
if [[ "$FAMILY" == fedora && "$ID" == fedora ]] && ! version_ge "${VERSION_ID:-0}" 44 && [[ "${VERSION_ID:-}" != rawhide ]]; then
  die "Fedora ${VERSION_ID} is too old: Hyprland 0.56 (needed for the Lua config) is built for Fedora 44 and newer."
fi
if [[ "$FAMILY" == ubuntu ]] && ! version_ge "${VERSION_ID:-0}" 26.04; then
  die "$NAME_SHOWN is too old: it lacks gtk4-layer-shell and a recent Waybar. Ubuntu/Kubuntu 26.04 LTS or newer is needed."
fi
say "Installing Summer Hyprland on $NAME_SHOWN ($FAMILY family)"

# ---------------------------------------------------------------- packages
FEDORA_PKGS=(
  hyprland hyprlock hypridle xdg-desktop-portal-hyprland
  waybar swaybg SwayNotificationCenter kitty nemo
  python3-gobject gtk4 gtk4-layer-shell
  qalculate cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  pulseaudio-utils bluez NetworkManager upower ddcutil libnotify jq plocate localsearch
  mate-polkit xdg-utils google-noto-color-emoji-fonts vazirmatn-fonts
  git curl tar
)
ARCH_PKGS=(
  hyprland hyprlock hypridle xdg-desktop-portal-hyprland
  waybar swaybg swaync kitty nemo
  python-gobject gtk4 gtk4-layer-shell
  libqalculate cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  libpulse bluez bluez-utils networkmanager upower power-profiles-daemon ddcutil libnotify jq
  plocate localsearch mate-polkit xdg-utils ttf-jetbrains-mono-nerd noto-fonts-emoji
  git curl unzip
)
UBUNTU_PKGS=(
  hyprland hyprlock hypridle xdg-desktop-portal-hyprland
  waybar swaybg sway-notification-center kitty nemo
  python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0
  qalc cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  pulseaudio-utils bluez network-manager upower power-profiles-daemon ddcutil libnotify-bin jq
  plocate localsearch mate-polkit xdg-utils fonts-noto-color-emoji fonts-vazirmatn
  git curl tar
)

install_packages() {
  case "$FAMILY" in
    fedora)
      say "Hyprland 0.56+ comes from the lionheartp/Hyprland COPR"
      run sudo dnf install -y dnf-plugins-core
      run sudo dnf copr enable -y lionheartp/Hyprland
      run sudo dnf install -y "${FEDORA_PKGS[@]}" ;;
    arch)
      run sudo pacman -Syu --needed --noconfirm "${ARCH_PKGS[@]}" ;;
    ubuntu)
      say "Hyprland 0.56+ comes from the cppiber/hyprland PPA"
      run sudo apt-get update
      run sudo apt-get install -y software-properties-common
      run sudo add-apt-repository -y ppa:cppiber/hyprland
      run sudo apt-get update
      run sudo apt-get install -y "${UBUNTU_PKGS[@]}" ;;
  esac
}

# ---------------------------------------------------------------- fonts
fetch_font() {  # folder "font family" url
  local name="$1" family="$2" url="$3" tmp
  # (grep without -q: with pipefail, -q quitting early would make fc-list fail)
  if fc-list : family 2>/dev/null | grep -i -- "$family" >/dev/null; then say "$family already installed"; return; fi
  say "Downloading the $name font"
  ((DRY)) && { printf '   [dry-run] %s -> %s\n' "$url" "$FONTS/$name"; return; }
  tmp="$(mktemp -d)"
  if curl -fsSL "$url" -o "$tmp/font.archive"; then
    mkdir -p "$FONTS/$name"
    case "$url" in
      *.tar.xz) tar -xJf "$tmp/font.archive" -C "$FONTS/$name" ;;
      *.zip) unzip -qo "$tmp/font.archive" -d "$tmp/x" && find "$tmp/x" -name '*.ttf' -exec cp {} "$FONTS/$name/" \; ;;
    esac
  else
    warn "Couldn't download $name; install it yourself later."
  fi
  rm -rf "$tmp"
}

install_fonts() {
  if [[ "$FAMILY" != arch ]]; then   # Arch packages it (ttf-jetbrains-mono-nerd)
    fetch_font JetBrainsMonoNerd "JetBrainsMono Nerd Font" "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.tar.xz"
  fi
  if [[ "$FAMILY" == arch ]]; then   # Fedora and Ubuntu package Vazirmatn
    local url
    url="$(curl -fsSL https://api.github.com/repos/rastikerdar/vazirmatn/releases/latest 2>/dev/null |
           grep -o '"browser_download_url": *"[^"]*\.zip"' | head -1 | cut -d'"' -f4 || true)"
    [[ -n "$url" ]] && fetch_font Vazirmatn "Vazirmatn" "$url" || warn "Couldn't find the Vazirmatn font (Persian text); install it yourself later."
  fi
  run fc-cache -f "$FONTS" >/dev/null 2>&1 || true
}

# ---------------------------------------------------------------- configs
install_configs() {
  local stamp backup
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup="$CONFIG/summer-hyprland-backup-$stamp"
  for d in hypr waybar swaync; do
    if [[ -e "$CONFIG/$d" ]]; then
      say "Backing up ~/.config/$d -> ${backup/#$HOME/\~}/$d"
      run mkdir -p "$backup"
      run mv "$CONFIG/$d" "$backup/$d"
    fi
  done
  say "Copying the configs to ~/.config"
  run mkdir -p "$CONFIG"
  run cp -r "$HERE/config/hypr" "$HERE/config/waybar" "$HERE/config/swaync" "$CONFIG/"
  run mkdir -p "$CONFIG/systemd/user"
  run cp "$HERE/config/systemd/user/hyprland-session.target" "$CONFIG/systemd/user/"
  if ((!DRY)); then
    sed -i "s|@HOME@|$HOME|g" "$CONFIG/hypr/hyprlock.conf"
    sed -i "s|^local themeName = \".*\"|local themeName = \"summer-$THEME\"|" "$CONFIG/hypr/hyprland.lua"
    chmod +x "$CONFIG"/hypr/scripts/*.sh "$CONFIG"/waybar/scripts/*.sh "$CONFIG"/waybar/scripts/*.py
  fi

  # wallpapers and kitty colors belong to the original rice: fetch just those files
  # from it (the repo itself is ~200 MB of Photoshop sources)
  say "Fetching wallpapers from the original rice ($UPSTREAM)"
  local raw="${UPSTREAM/github.com/raw.githubusercontent.com}/main" f
  run mkdir -p "$CONFIG/hypr/wallpapers"
  for f in summer-day.png summer-night.png; do
    run curl -fsSL "$raw/wallpapers/$f" -o "$CONFIG/hypr/wallpapers/$f" ||
      warn "Couldn't download $f; put it in ~/.config/hypr/wallpapers/ yourself."
  done
  if [[ ! -e "$CONFIG/kitty/kitty.conf" ]]; then
    say "Adding the original rice's kitty colors (you had no kitty config)"
    run mkdir -p "$CONFIG/kitty/colors"
    for f in kitty.conf colors/everforest.conf colors/everforest-light.conf; do
      run curl -fsSL "$raw/kitty/$f" -o "$CONFIG/kitty/$f" || warn "Couldn't download kitty/$f."
    done
  fi
}

# ---------------------------------------------------------------- services
enable_services() {
  # file search: the index for file names, and GNOME's indexer for names + contents
  run sudo systemctl enable --now plocate-updatedb.timer 2>/dev/null || true
  ((DRY)) || (sudo updatedb >/dev/null 2>&1 &) || true
  run systemctl --user enable --now localsearch-3.service 2>/dev/null || true
  run sudo systemctl enable --now bluetooth.service 2>/dev/null || true
}

# ---------------------------------------------------------------- go
echo
echo "This will:"
((PACKAGES)) && echo "  • install packages with sudo (Hyprland 0.56+, Waybar, GTK4 layer shell, ...)"
((PACKAGES)) && echo "  • download fonts to ${FONTS/#$HOME/\~} if missing"
echo "  • move your ~/.config/hypr, waybar and swaync to a backup folder, and copy these in"
echo "  • download the wallpapers from the original rice"
echo
ask "Continue?" || { echo "Nothing changed."; exit 0; }

if ((PACKAGES)); then install_packages; install_fonts; fi
install_configs
((PACKAGES)) && enable_services

echo
say "Done. Log out and pick \"Hyprland\" on the login screen."
echo "    SUPER+D search · SUPER+Return terminal · SUPER+C calculator · SUPER+V clipboard · SUPER+. emoji"
echo "    Screens: add your layout to ~/.config/hypr/hyprland.lua (see the Monitors section)."
