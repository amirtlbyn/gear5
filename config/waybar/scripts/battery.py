#!/usr/bin/env python3
"""
Battery charge limits: the reads, the rule, and the user service. No GTK here —
the service imports this file directly, and so does the Battery page's panel
(battery-page.py), so the page and the service can never disagree.

  battery.py --serve      the battery-limits user service: apply the rule at
                          start, every 30 s, and within about 2 s of a settings
                          change (a 1 s check of user-settings.json's mtime)

The firmware's own charge_types offers only Fast / Standard / Long_Life, and
Long_Life just holds the level near 80%: there is no free stop/start threshold.
rule() adds one with hysteresis over Long_Life (BATPICK-3), so the charger does
not flip on and off around a single level.

    import battery
    state = battery.read()                      # capacity, status, health, cycles, watts…
    stop, start, speed = battery.valid(s["battery_stop"], s["battery_start"], s["battery_speed"])
    wanted = battery.rule(state["capacity"], stop, start, speed, state["charge_type"])
    battery.apply(wanted)                        # writes charge_types only when it differs
"""
import glob
import os
import sys
import time

import settings_store as store

SYSFS = "/sys/class/power_supply"
POLL_SECONDS = 30
CHECK_SECONDS = 1
SPEEDS = ("Fast", "Standard")
FULL = (100, 95, store.DEFAULTS["battery_speed"])  # the safe fallback: no limit (INV-1)


def _read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def _read_int(path):
    try:
        return int(_read_text(path))
    except (TypeError, ValueError):
        return None


def battery_name(sysfs=SYSFS):
    """The first BAT* supply, or None on hardware with no battery."""
    paths = sorted(glob.glob(os.path.join(sysfs, "BAT*")))
    return os.path.basename(paths[0]) if paths else None


def charge_options(sysfs=SYSFS):
    """The names charge_types offers, brackets removed ("Fast [Standard] Long_Life"
    -> ["Fast", "Standard", "Long_Life"]); [] with no battery or no charge_types."""
    name = battery_name(sysfs)
    text = _read_text(os.path.join(sysfs, name, "charge_types")) if name else None
    return [w.strip("[]") for w in text.split()] if text else []


def supported(sysfs=SYSFS):
    """Whether charge_types offers Long_Life and both speeds, as the IdeaPad's does.
    Elsewhere (no charge_types, or another vendor's names, e.g. a Dell's
    Trickle/Adaptive/Custom) the page is read-only and nothing is ever written."""
    return {"Long_Life", *SPEEDS} <= set(charge_options(sysfs))


def ac_name(sysfs=SYSFS):
    """The first Mains supply (the AC adapter), or None."""
    for path in sorted(glob.glob(os.path.join(sysfs, "*"))):
        if _read_text(os.path.join(path, "type")) == "Mains":
            return os.path.basename(path)
    return None


def read_charge_type(sysfs=SYSFS):
    """The bracketed name in charge_types ("Fast [Standard] Long_Life" ->
    "Standard"), or None with no battery, an unreadable file, or no bracket."""
    name = battery_name(sysfs)
    text = _read_text(os.path.join(sysfs, name, "charge_types")) if name else None
    if not text:
        return None
    return next((w[1:-1] for w in text.split() if w.startswith("[") and w.endswith("]")), None)


def writable(sysfs=SYSFS):
    """Whether this process can write charge_types (the udev rule ran, BATPICK-5)."""
    return supported(sysfs) and os.access(os.path.join(sysfs, battery_name(sysfs), "charge_types"), os.W_OK)


def read(sysfs=SYSFS):
    """Status, health (full ÷ design capacity), cycle count and power draw
    (BATPICK-1), or None on hardware with no battery."""
    name = battery_name(sysfs)
    if name is None:
        return None
    base = os.path.join(sysfs, name)
    ac = ac_name(sysfs)
    full = _read_int(os.path.join(base, "energy_full"))
    design = _read_int(os.path.join(base, "energy_full_design"))
    power_now = _read_int(os.path.join(base, "power_now"))
    return dict(
        status=_read_text(os.path.join(base, "status")) or "Unknown",
        capacity=_read_int(os.path.join(base, "capacity")),
        health_pct=round(full * 100 / design) if full and design else None,
        cycle_count=_read_int(os.path.join(base, "cycle_count")),
        power_watts=round(power_now / 1_000_000, 1) if power_now is not None else None,
        on_ac=(_read_text(os.path.join(sysfs, ac, "online")) == "1") if ac else None,
        charge_type=read_charge_type(sysfs),
        supported=supported(sysfs),
    )


def valid(stop, start, speed):
    """stop and start as whole numbers, speed as Fast or Standard; raises
    ValueError otherwise (BATPICK-6): a hand-edited file must not be able to
    stop the battery from charging — the caller falls back to FULL instead."""
    try:
        stop, start = int(stop), int(start)
    except (TypeError, ValueError):
        raise ValueError("Stop and start must be whole numbers") from None
    if not 80 <= stop <= 100:
        raise ValueError("Stop charging at must be 80-100")
    if not 40 <= start <= stop - 5:
        raise ValueError(f"Start charging at must be 40-{stop - 5}")
    if speed not in SPEEDS:
        raise ValueError("Speed must be Fast or Standard")
    return stop, start, speed


def rule(capacity, stop, start, speed, current):
    """The charge type this moment calls for (BATPICK-3): Long_Life whenever
    stop is the firmware's 80% hold, or the level is at or above stop; the
    chosen speed whenever stop is 100 (no limit), or the level is at or below
    start; the current type in between, so it does not flip back and forth."""
    if stop == 80 or (capacity is not None and capacity >= stop):
        return "Long_Life"
    if stop == 100 or (capacity is not None and capacity <= start):
        return speed
    return current


def apply(charge_type, sysfs=SYSFS):
    """Write charge_types, but only when it differs from the current value
    (BATPICK-4). Returns True on a write, False when nothing changed or the
    write failed — a failed write never stops the caller from trying again."""
    if not supported(sysfs) or charge_type not in ("Long_Life", *SPEEDS):
        return False
    if charge_type == read_charge_type(sysfs):
        return False
    try:
        with open(os.path.join(sysfs, battery_name(sysfs), "charge_types"), "w") as f:
            f.write(charge_type)
        return True
    except OSError:
        return False


def tick(sysfs=SYSFS, config=None):
    """One pass of the service: read the saved settings and the battery, and
    apply the charge type the rule calls for. A bad saved value falls back to
    FULL (BATPICK-6); a read or write failure is skipped, not raised — the
    next tick tries again (BATPICK-4)."""
    try:
        s = store.load(config) if config is not None else store.load()
        stop, start, speed = valid(s["battery_stop"], s["battery_start"], s["battery_speed"])
    except ValueError:
        stop, start, speed = FULL
    state = read(sysfs)
    if state is None:
        return
    apply(rule(state["capacity"], stop, start, speed, state["charge_type"]), sysfs)


def serve(sysfs=SYSFS, config=None, iterations=None, sleep=time.sleep):
    """The battery-limits user service (BATPICK-4): apply the rule now, then
    keep it applied — a 30 s timer, and a 1 s check of user-settings.json's
    mtime, so a settings change reaches the battery within about 2 s. Never
    raises: `tick` swallows its own read/write/value failures. `iterations`
    stops the loop after that many checks (tests only); the real service loops
    forever."""
    last_mtime, last_poll, checks = None, 0.0, 0
    json_path = (store.paths(config) if config is not None else store.paths())[0]
    while iterations is None or checks < iterations:
        try:
            mtime = os.path.getmtime(json_path)
        except OSError:
            mtime = None
        now = time.monotonic()
        if checks == 0 or mtime != last_mtime or now - last_poll >= POLL_SECONDS:
            last_mtime, last_poll = mtime, now
            tick(sysfs, config)
        checks += 1
        sleep(CHECK_SECONDS)


if __name__ == "__main__":
    if "--serve" in sys.argv:
        serve()
