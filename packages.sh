# The packages Gear5 needs, per distribution family: install.sh installs them,
# doctor.sh checks that they are installed. Read with `. packages.sh`.
# quickshell runs the lock screen (spec QSL). Fedora: COPR errornointernet/quickshell
# (install.sh enables it). Arch: extra. Ubuntu: if 26.04 lacks the package, build it from
# https://quickshell.org and keep `qs` on PATH.
FEDORA_PKGS=(
  hyprland hyprlock quickshell hypridle xdg-desktop-portal-hyprland
  waybar swaybg SwayNotificationCenter kitty nemo
  python3-gobject gtk4 gtk4-layer-shell
  qalculate cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  pulseaudio-utils bluez NetworkManager upower ddcutil libnotify jq socat plocate localsearch
  mate-polkit xdg-utils google-noto-color-emoji-fonts vazirmatn-fonts hyprpicker wlsunset
  git curl tar
)
ARCH_PKGS=(
  hyprland hyprlock quickshell hypridle xdg-desktop-portal-hyprland
  waybar swaybg swaync kitty nemo
  python-gobject gtk4 gtk4-layer-shell
  libqalculate cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  libpulse bluez bluez-utils networkmanager upower power-profiles-daemon ddcutil libnotify jq socat
  plocate localsearch mate-polkit xdg-utils ttf-jetbrains-mono-nerd noto-fonts-emoji hyprpicker wlsunset
  git curl unzip
)
UBUNTU_PKGS=(
  hyprland hyprlock quickshell hypridle xdg-desktop-portal-hyprland
  waybar swaybg sway-notification-center kitty nemo
  python3-gi python3-gi-cairo gir1.2-pango-1.0 gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0
  qalc cliphist wl-clipboard grim slurp swappy playerctl brightnessctl pavucontrol
  pulseaudio-utils bluez network-manager upower power-profiles-daemon ddcutil libnotify-bin jq socat
  plocate localsearch mate-polkit xdg-utils fonts-noto-color-emoji fonts-vazirmatn hyprpicker wlsunset
  git curl tar
)
