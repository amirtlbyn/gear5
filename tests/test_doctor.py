"""doctor.sh finds each fault we cause on purpose and prints its fix (spec DOCTOR).
Each test builds a healthy fake system (fake package manager, systemctl and
findmnt, a fake udev folder and sysfs, stub popup processes), breaks one thing,
and runs the real doctor.sh against it."""

import os
import shutil
import signal
import subprocess

import pytest
from conftest import ROOT, SCRIPTS

DOCTOR = os.path.join(ROOT, "doctor.sh")
RULE = os.path.join(ROOT, "config", "udev", "90-summer-battery.rules")
PORTALS = ["xdg-desktop-portal.service", "xdg-desktop-portal-hyprland.service", "xdg-document-portal.service"]
FAMILIES = {  # os-release ID -> (the package list, the fake query program, the install command)
    "fedora": ("FEDORA_PKGS", "rpm", "sudo dnf install"),
    "arch": ("ARCH_PKGS", "pacman", "sudo pacman -S --needed"),
    "ubuntu": ("UBUNTU_PKGS", "dpkg-query", "sudo apt-get install"),
}


def package_list(name):
    out = subprocess.run(
        ["bash", "-c", f'. "{ROOT}/packages.sh"; printf "%s\\n" "${{{name}[@]}}"'],
        capture_output=True, text=True, check=True,
    ).stdout
    return out.split()


class System:
    def __init__(self, tmp, family="fedora"):
        self.tmp = tmp
        self.bin = tmp / "bin"
        self.bin.mkdir()
        self.home = tmp / "home"
        self.scripts = self.home / ".config" / "waybar" / "scripts"
        self.scripts.mkdir(parents=True)
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.home / ".config"),
            XDG_RUNTIME_DIR=str(tmp / "run"),
            PATH=f"{self.bin}:{os.environ['PATH']}",
            OS_RELEASE=str(tmp / "os-release"),
            UDEV_RULES_DIR=str(tmp / "udev"),
            POWER_SUPPLY=str(tmp / "power_supply"),
            HYPRLAND_INSTANCE_SIGNATURE="test",
        )
        self.pids = []
        # packages: all installed
        list_name, query, _ = FAMILIES[family]
        (tmp / "os-release").write_text(f"ID={family}\n")
        self.installed = tmp / "installed"
        self.installed.write_text("\n".join(package_list(list_name)) + "\n")
        pkg = {"rpm": '"$2"', "pacman": '"$2"', "dpkg-query": '"$3"'}[query]
        found = {"dpkg-query": 'printf "install ok installed"; exit 0'}.get(query, "exit 0")
        self.fake(query, f'rg -qx -- {pkg} "{self.installed}" && {{ {found}; }}; exit 1')
        # the udev rule and a battery with charge_types
        (tmp / "udev").mkdir()
        shutil.copy(RULE, tmp / "udev")
        (tmp / "power_supply" / "BAT0").mkdir(parents=True)
        self.charge_types = tmp / "power_supply" / "BAT0" / "charge_types"
        self.charge_types.write_text("Fast [Standard] Long_Life\n")
        # services: every one enabled and active; systemctl logs each call
        self.active = tmp / "active"
        self.active.write_text("\n".join(["battery-limits.service", "night-light.service", "bar-gif.service", *PORTALS]) + "\n")
        self.enabled = tmp / "enabled"
        self.enabled.write_text("battery-limits.service\nnight-light.service\nbar-gif.service\n")
        self.calls = tmp / "systemctl.log"
        self.fake("systemctl", f'''echo "$*" >> "{self.calls}"
case "$2" in
  is-active)  rg -qx -- "$3" "{self.active}" && echo active || echo inactive ;;
  is-enabled) rg -qx -- "$3" "{self.enabled}" && echo enabled || echo disabled ;;
esac''')
        dropin = self.home / ".config" / "systemd" / "user" / "xdg-document-portal.service.d"
        dropin.mkdir(parents=True)
        self.dropin = dropin / "restart.conf"
        self.dropin.write_text("[Service]\nRestart=on-failure\n")
        # the document portal's mount
        self.fstype = tmp / "fstype"
        self.fstype.write_text("fuse.portal")
        self.fake("findmnt", f'[ -s "{self.fstype}" ] && cat "{self.fstype}" && echo || exit 1')
        # popup.sh (for its list) and every popup running
        shutil.copy(os.path.join(SCRIPTS, "popup.sh"), self.scripts)
        self.popups = {}
        for name in self.popup_names():
            stub = self.scripts / f"{name}.py"
            stub.write_text("#!/bin/sh\nsleep 60\n")
            stub.chmod(0o755)
            self.popups[name] = self.start(str(stub), "zoro", "--hidden")

    def fake(self, name, body):
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def popup_names(self):
        for line in open(os.path.join(SCRIPTS, "popup.sh")):
            if line.startswith('all="'):
                return line.split('"')[1].split()

    def start(self, *argv):
        out = subprocess.run(
            ["bash", "-c", 'setsid "$@" >/dev/null 2>&1 & echo $!', "start", *argv],
            env=self.env, capture_output=True, text=True, check=True,
        ).stdout
        self.pids.append(int(out))
        return int(out)

    def remove_line(self, path, line):
        lines = path.read_text().splitlines()
        path.write_text("".join(f"{x}\n" for x in lines if x != line))

    def run(self):
        done = subprocess.run([DOCTOR], env=self.env, capture_output=True, text=True, timeout=30)
        return done.returncode, done.stdout

    def cleanup(self):
        for pid in self.pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.fixture
def system(tmp_path):
    s = System(tmp_path)
    yield s
    s.cleanup()


def fails(out):
    """The FAIL lines, each with its fix line."""
    lines = out.splitlines()
    return [(line, lines[i + 1]) for i, line in enumerate(lines) if line.startswith("FAIL")]


def test_a_healthy_system_passes(system):
    """DOCTOR-1: given a system where every check passes, when doctor.sh runs,
    then it prints only ok lines (one per check) and exits 0; and it asks
    systemctl only is-active / is-enabled (it changes nothing)."""
    code, out = system.run()

    assert code == 0, out
    assert fails(out) == []
    assert [line.split()[0] for line in out.splitlines() if line.strip()][:-1] == ["ok"] * 12  # bar-gif.service is the 12th check
    verbs = {call.split()[1] for call in system.calls.read_text().splitlines()}
    assert verbs <= {"is-active", "is-enabled"}


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_missing_packages_are_named_with_one_install_command(tmp_path, family):
    """DOCTOR-2: given Fedora, Arch, or Ubuntu with two packages of its list not
    installed, when doctor.sh runs, then one FAIL names both, and its fix is
    that family's install command with both names."""
    s = System(tmp_path, family)
    try:
        wanted = package_list(FAMILIES[family][0])
        gone = [wanted[3], wanted[-1]]
        for p in gone:
            s.remove_line(s.installed, p)

        code, out = s.run()
    finally:
        s.cleanup()

    assert code == 1
    (fail, fix), = fails(out)
    assert fail == f"FAIL  packages not installed: {' '.join(gone)}"
    assert fix == f"      fix: {FAMILIES[family][2]} {' '.join(gone)}"


@pytest.mark.parametrize("fault", ["missing", "outdated", "not writable"])
def test_a_udev_rule_fault_is_reported_with_its_fix(system, fault):
    """DOCTOR-3: given a battery with charge_types, when the udev rule is
    missing, differs from the repository copy, or charge_types is not writable,
    then doctor.sh reports that one fault; the fix installs and applies the rule
    (missing, outdated) or applies it (not writable)."""
    rule = system.tmp / "udev" / "90-summer-battery.rules"
    if fault == "missing":
        rule.unlink()
    elif fault == "outdated":
        rule.write_text(rule.read_text().replace("RUN+=", "RUN += ", 1))
    else:
        system.charge_types.chmod(0o444)

    code, out = system.run()

    assert code == 1
    (fail, fix), = fails(out)
    assert {"missing": "not installed", "outdated": "differs", "not writable": "not writable"}[fault] in fail
    assert "udevadm trigger --subsystem-match=power_supply" in fix
    assert ("sudo install -m644" in fix) == (fault != "not writable")


@pytest.mark.parametrize("fault", ["battery-limits stopped", "battery-limits disabled", *PORTALS, "drop-in"])
def test_a_service_fault_is_reported_with_its_fix(system, fault):
    """DOCTOR-4: given battery-limits stopped or disabled, one of the three
    portal services not active, or the document portal drop-in missing, when
    doctor.sh runs, then it reports that one fault with its fix."""
    if fault == "battery-limits stopped":
        system.remove_line(system.active, "battery-limits.service")
    elif fault == "battery-limits disabled":
        system.remove_line(system.enabled, "battery-limits.service")
    elif fault == "drop-in":
        system.dropin.unlink()
    else:
        system.remove_line(system.active, fault)

    code, out = system.run()

    assert code == 1
    (fail, fix), = fails(out)
    if fault.startswith("battery-limits"):
        assert fix == "      fix: systemctl --user enable --now battery-limits.service"
    elif fault == "drop-in":
        assert "restart.conf" in fail and "systemctl --user daemon-reload" in fix
    else:
        assert fail.startswith(f"FAIL  {fault} is not running")
        assert fix == f"      fix: systemctl --user restart {fault}"


def test_a_running_document_portal_without_its_mount_is_reported(system):
    """DOCTOR-5: given xdg-document-portal active and nothing mounted on
    $XDG_RUNTIME_DIR/doc, when doctor.sh runs, then it reports the missing mount
    and prints the restart command."""
    system.fstype.write_text("")

    code, out = system.run()

    assert code == 1
    (fail, fix), = fails(out)
    assert fail == f"FAIL  the document portal runs, but {system.tmp}/run/doc is not mounted"
    assert fix == "      fix: systemctl --user restart xdg-document-portal.service"


def test_a_missing_or_paused_popup_is_named(system):
    """DOCTOR-6: given one popup not running and another paused (SIGSTOP), when
    doctor.sh runs, then one FAIL names both (the paused one marked) and the fix
    is popup.sh --restart; given no popup.sh at all, it says the configs are
    not installed (not "0 running")."""
    os.kill(system.popups["calculator"], signal.SIGKILL)
    os.kill(system.popups["launcher"], signal.SIGSTOP)

    code, out = system.run()

    assert code == 1
    (fail, fix), = fails(out)
    assert fail == "FAIL  popups not running: calculator, launcher (paused)"
    assert fix == "      fix: ~/.config/waybar/scripts/popup.sh --restart"

    (system.scripts / "popup.sh").unlink()
    code, out = system.run()
    (fail, fix), = fails(out)
    assert fail.endswith("popup.sh is missing: the configs are not installed")
    assert fix == "      fix: ./install.sh --configs-only"
