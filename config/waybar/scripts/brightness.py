"""Screen brightness: read and set, for the laptop backlight, external screens
over DDC/CI, and a software dimmer for screens that can't change their own. The
quick settings card and Settings' Displays row share this module, so both see
and change the same thing."""
import json
import os
import re
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
DIM_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "screen-dim")
VENDORS = {"SAM": "Samsung", "MSI": "MSI", "DEL": "Dell", "GSM": "LG", "ACR": "Acer", "AUS": "ASUS",
           "BNQ": "BenQ", "HWP": "HP", "LEN": "Lenovo", "PHL": "Philips", "AOC": "AOC", "VSC": "ViewSonic",
           "GBT": "Gigabyte", "HPN": "HP", "SNY": "Sony", "XMI": "Xiaomi", "MIC": "MSI"}
DDC_CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                         "control-center", "ddc.json")


def run(*cmd, timeout=10):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


def spawn(*cmd):
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


def laptop_brightness():
    code, out, _ = run("brightnessctl", "-m", "-c", "backlight", timeout=3)
    parts = out.strip().split(",")
    if code != 0 or len(parts) < 4:
        return None
    try:
        return int(parts[3].rstrip("%"))
    except ValueError:
        return None


def ddc_displays(connected):
    """External screens that take brightness over the cable (DDC/CI).
    Finding them is slow, so the answer is kept until the set of screens changes."""
    key = ["v2"] + sorted(connected)
    try:
        with open(DDC_CACHE) as f:
            cache = json.load(f)
        if cache.get("screens") == key:
            return cache["displays"]
    except (OSError, ValueError, KeyError):
        pass
    _, out, _ = run("ddcutil", "detect", "--terse", timeout=60)
    displays = []
    for block in out.split("\n\n"):
        bus = re.search(r"/dev/i2c-(\d+)", block)
        mon = re.search(r"Monitor:\s+(.+)", block)
        conn = re.search(r"DRM connector:\s+card\d+-(\S+)", block)
        if not block.startswith("Display") or not bus:
            continue
        mfg, model = (mon.group(1).split(":") + ["", ""])[:2] if mon else ("", "")
        name = " ".join(x for x in (VENDORS.get(mfg, mfg), model.replace(VENDORS.get(mfg, mfg), "").strip()) if x)
        displays.append(dict(bus=int(bus.group(1)), name=name or f"Screen {bus.group(1)}",
                             output=conn.group(1) if conn else None))
    try:
        os.makedirs(os.path.dirname(DDC_CACHE), exist_ok=True)
        with open(DDC_CACHE, "w") as f:
            json.dump(dict(screens=key, displays=displays), f)
    except OSError:
        pass
    return displays


def read_screens():
    """Brightness of every screen that can change it: the laptop panel (when it is on)
    and external screens with DDC/CI."""
    try:
        mons = json.loads(run("hyprctl", "-j", "monitors", timeout=3)[1])
    except ValueError:
        mons = []
    mons.sort(key=lambda m: (m.get("x", 0), m.get("y", 0)))   # left to right, like the desk
    names = [m["name"] for m in mons]
    externals = [n for n in names if not re.match(r"eDP|LVDS|DSI", n)]
    ddc = {d["output"]: d for d in ddc_displays(names)} if externals else {}
    screens = []
    for m in mons:
        out = m["name"]
        if re.match(r"eDP|LVDS|DSI", out):
            value = laptop_brightness()
            if value is not None:
                screens.append(dict(key="laptop", name="Laptop", how="backlight", value=value,
                                    output=out))
            continue
        d = ddc.get(out)
        if d:
            _, text, _ = run("ddcutil", "--bus", str(d["bus"]), "getvcp", "10", "--terse", timeout=10)
            v = re.search(r"VCP 10 C (\d+) (\d+)", text)
            if v and int(v.group(2)) > 0:
                screens.append(dict(key=f"ddc:{d['bus']}", name=d["name"], how="hardware",
                                    value=round(int(v.group(1)) * 100 / int(v.group(2))),
                                    max=int(v.group(2)), output=out))
                continue
        # no DDC/CI (e.g. through a dock): dim it in software instead
        model = m.get("model") or out
        make = VENDORS.get((m.get("make") or "")[:3].upper(), m.get("make") or "")
        name = model if make.lower() in model.lower() or not make else f"{make} {model}"
        screens.append(dict(key=f"dim:{out}", name=name, how="dimmed",
                            value=dim_level(out), output=out))
    return screens


def dim_level(output):
    try:
        with open(os.path.join(DIM_DIR, output)) as f:
            return max(10, min(100, int(f.read().strip())))
    except (OSError, ValueError):
        return 100


# DDC write queue: a monitor takes ~0.1 s per change, so send only the latest
# value per bus, one at a time
_pending, _busy, _lock = {}, set(), threading.Lock()


def set(sc, value):
    """Set one screen's brightness (sc is a dict from read_screens)."""
    if sc["key"] == "laptop":
        spawn("brightnessctl", "-q", "-c", "backlight", "set", f"{value}%")
        return
    if sc["key"].startswith("dim:"):
        output = sc["key"][4:]
        try:
            os.makedirs(DIM_DIR, exist_ok=True)
            with open(os.path.join(DIM_DIR, output), "w") as f:
                f.write(str(value))
        except OSError:
            return
        if value < 100:   # does nothing if this screen's dimmer is already running
            spawn(sys.executable, os.path.join(HERE, "dim-screen.py"), output)
        return
    bus = sc["key"].split(":")[1]
    with _lock:
        _pending[bus] = round(value * sc["max"] / 100)
        if bus in _busy:
            return
        _busy.add(bus)

    def work():
        while True:
            with _lock:
                target = _pending.pop(bus, None)
                if target is None:
                    _busy.discard(bus)
                    return
            run("ddcutil", "--bus", bus, "--noverify", "setvcp", "10", str(target), timeout=10)
    threading.Thread(target=work, daemon=True).start()
