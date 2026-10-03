"""
LIVE test of the overview (spec OVERVIEW) on your desktop. Run it on the
desktop, not in CI, with the configs installed:

    python3 tests/live_overview.py

OVERVIEW-6: it starts the installed overview with 20 windows (copies of the
windows you have open, spread over desks 1-5, so their captures are real), opens
it with `popup.sh overview` 1 + 3 times, and times each open from the call to
Hyprland's `openlayer>>overview` event. The median of the 3 warm opens must be
150 ms or less. It also times 20 captures in parallel (the thumbnails arrive
after the open).

It also calls goToWindow on a window on another desk, checks that every
screen went to that desk and the window has focus, then goes back to your
window.

At the end the normal hidden overview runs again.
"""

import json
import os
import socket
import statistics
import subprocess
import sys
import tempfile
import threading
import time

SCRIPTS = os.path.expanduser("~/.config/waybar/scripts")
sys.path.insert(0, SCRIPTS)
import thumbs  # noqa: E402

POPUP = os.path.join(SCRIPTS, "popup.sh")
OVERVIEW = os.path.join(SCRIPTS, "overview.py")
EVENTS = os.path.join(
    os.environ["XDG_RUNTIME_DIR"], "hypr", os.environ["HYPRLAND_INSTANCE_SIGNATURE"], ".socket2.sock"
)


def hypr(*args):
    return json.loads(subprocess.run(["hyprctl", "-j", *args], capture_output=True, text=True).stdout)


def desk_of(ws_id):
    return (ws_id - 1) % 10 + 1


def fake_clients(real, count=20):
    """count windows: copies of the real ones (their stableId, so the captures are
    real), with made-up addresses, spread over desks 1-5 on the screens you have."""
    monitors = hypr("monitors")
    shown = [c for c in real if c.get("workspace", {}).get("id", 0) >= 1] or real
    out = []
    for i in range(count):
        c = dict(shown[i % len(shown)])
        m = monitors[i % len(monitors)]
        slot = (m["activeWorkspace"]["id"] - 1) // 10
        c["address"] = hex(0x9000 + i)
        c["monitor"] = m["id"]
        c["workspace"] = {"id": slot * 10 + 1 + i % 5, "name": str(slot * 10 + 1 + i % 5)}
        c["mapped"] = True
        out.append(c)
    return out


def start_overview(env=None):
    subprocess.run(["pkill", "-f", OVERVIEW])
    for _ in range(30):
        if subprocess.run(["pgrep", "-f", OVERVIEW], capture_output=True).returncode:
            break
        time.sleep(0.1)
    subprocess.Popen(
        ["setsid", OVERVIEW, "", "--hidden"],
        env={**os.environ, **(env or {})},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )
    for _ in range(50):  # until it owns its D-Bus name
        out = subprocess.run(
            ["gdbus", "call", "--session", "--dest", "org.freedesktop.DBus", "--object-path",
             "/org/freedesktop/DBus", "--method", "org.freedesktop.DBus.NameHasOwner", "io.local.overview"],
            capture_output=True, text=True,
        ).stdout
        if "true" in out:
            time.sleep(0.5)  # and has built its window
            return
        time.sleep(0.1)
    raise SystemExit("FAIL the overview did not start")


class Events:
    def __init__(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(EVENTS)
        self.sock.settimeout(3)
        self.buf = b""

    def wait(self, line):
        """Seconds until Hyprland sends `line` (after the call that started the clock)."""
        want = line.encode()
        while True:
            while b"\n" in self.buf:
                got, self.buf = self.buf.split(b"\n", 1)
                if got == want:
                    return time.monotonic()
            self.buf += self.sock.recv(65536)


def time_opens(runs=4):
    events = Events()
    times = []
    for _ in range(runs):
        t0 = time.monotonic()
        subprocess.run([POPUP, "overview"])
        times.append((events.wait("openlayer>>overview") - t0) * 1000)
        time.sleep(0.4)
        subprocess.run([POPUP, "--close-all"])
        events.wait("closelayer>>overview")
        time.sleep(0.4)
    return times[1:]  # the first open warms the caches


def time_captures(clients):
    folder = tempfile.mkdtemp(dir=os.environ["XDG_RUNTIME_DIR"])
    paths = []
    t0 = time.monotonic()
    workers = [threading.Thread(target=lambda c=c: paths.append(thumbs.capture(c, folder))) for c in clients]
    for w in workers:
        w.start()
    for w in workers:
        w.join()
    took = (time.monotonic() - t0) * 1000
    for p in paths:
        if p:
            os.remove(p)
    os.rmdir(folder)
    return took, sum(p is not None for p in paths)


def check_go_to_window():
    clients = hypr("clients")
    here = hypr("activewindow")
    now = desk_of(hypr("activeworkspace")["id"])
    other = next((c for c in clients if c["workspace"]["id"] >= 1 and desk_of(c["workspace"]["id"]) != now), None)
    if other is None:
        print("skip goToWindow: no window on another desk")
        return True
    target = desk_of(other["workspace"]["id"])
    subprocess.run(["hyprctl", "eval", f'goToWindow("{other["address"]}")'], capture_output=True)
    time.sleep(0.4)
    focused = hypr("activewindow").get("address")
    desks = {desk_of(m["activeWorkspace"]["id"]) for m in hypr("monitors")}
    ok = focused == other["address"] and desks == {target}
    print(f"{'ok  ' if ok else 'FAIL'} goToWindow: desk {now} -> {target} on every screen, focus {other['class']}")
    # back to where you were
    if here.get("address"):
        subprocess.run(["hyprctl", "eval", f'goToWindow("{here["address"]}")'], capture_output=True)
    else:
        subprocess.run(["hyprctl", "eval", f"desk({now})"], capture_output=True)
    return ok


def main():
    real = hypr("clients")
    fake = fake_clients(real)
    with tempfile.NamedTemporaryFile("w", suffix=".json", dir=os.environ["XDG_RUNTIME_DIR"], delete=False) as f:
        json.dump(fake, f)
    try:
        start_overview({"OVERVIEW_CLIENTS": f.name})
        opens = time_opens()
    finally:
        start_overview()  # the normal one again
        os.remove(f.name)
    median = statistics.median(opens)
    ok_open = median <= 150
    print(f"{'ok  ' if ok_open else 'FAIL'} open with 20 windows: {', '.join(f'{t:.0f}' for t in opens)} ms "
          f"(median {median:.0f} ms, limit 150)")
    took, got = time_captures(fake)
    print(f"     20 captures in parallel: {took:.0f} ms ({got} thumbnails)")
    ok_go = check_go_to_window()
    return 0 if ok_open and ok_go else 1


if __name__ == "__main__":
    sys.exit(main())
