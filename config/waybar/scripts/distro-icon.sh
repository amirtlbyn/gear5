#!/usr/bin/env bash
# Logo of this Linux for the bar's launcher button (JetBrainsMono Nerd Font glyphs).
# Force one with ~/.config/waybar/distro, e.g.: echo arch > ~/.config/waybar/distro
id=""
[[ -r ~/.config/waybar/distro ]] && read -r id < ~/.config/waybar/distro
if [[ -z "$id" && -r /etc/os-release ]]; then
  . /etc/os-release
  id="$ID"
  # Kubuntu says "ubuntu" in os-release: look for its desktop instead
  if [[ "$id" == ubuntu ]] && { [[ -d /usr/share/kubuntu-default-settings ]] ||
       dpkg-query -W -f='${Status}' kubuntu-desktop 2>/dev/null | grep 'ok installed' >/dev/null; }; then
    id=kubuntu
  fi
  # unknown derivative: use its parent (ID_LIKE="arch", "ubuntu debian", "rhel fedora" ...)
  case "$id" in
    fedora|ubuntu|kubuntu|arch|debian|manjaro|endeavouros|pop|linuxmint|opensuse*|nixos|cachyos|garuda|artix|void|gentoo|alpine|zorin|elementary|kali|almalinux|rocky|centos) ;;
    *) for like in $ID_LIKE; do case "$like" in fedora|ubuntu|arch|debian) id="$like"; break ;; esac; done ;;
  esac
fi
case "$id" in
  fedora)       printf '' ;;
  kubuntu)      printf '' ;;
  ubuntu)       printf '' ;;
  arch)         printf '' ;;
  debian)       printf '' ;;
  manjaro)      printf '' ;;
  endeavouros)  printf '' ;;
  pop)          printf '' ;;
  linuxmint)    printf '' ;;
  opensuse*)    printf '' ;;
  nixos)        printf '' ;;
  cachyos)      printf '' ;;
  garuda)       printf '' ;;
  artix)        printf '' ;;
  void)         printf '' ;;
  gentoo)       printf '' ;;
  alpine)       printf '' ;;
  zorin)        printf '' ;;
  elementary)   printf '' ;;
  kali)         printf '' ;;
  almalinux)    printf '' ;;
  rocky)        printf '' ;;
  centos)       printf '' ;;
  *)            printf '' ;;   # Tux
esac
echo
