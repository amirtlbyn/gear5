"""Window thumbnails for the minimized picker and the overview: `grim -T` captures
one window by its stable ID (it works for windows on other desks and on the
minimized special desk too). Captures hold other windows' content, so they only
go in a folder of the private runtime dir, never in a shared /tmp."""
import os
import subprocess
import tempfile


def thumb_dir(name):
    """$XDG_RUNTIME_DIR/<name>, or None when there is no runtime dir (no captures then)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    return os.path.join(runtime, name) if runtime else None


def capture_cmd(stable_id, out_path):
    return ["grim", "-T", stable_id, out_path]


def capture(client, folder):
    """Run in a worker thread: the captured PNG's path, or None (no stableId, no
    folder, or grim failed — the caller shows the icon placeholder instead). The
    caller removes the file once it has loaded it."""
    stable_id = client.get("stableId")
    if not stable_id or not folder:
        return None
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        fd, path = tempfile.mkstemp(dir=folder, suffix=".png")  # one file per capture: no races
        os.close(fd)
    except OSError:
        return None
    try:
        r = subprocess.run(capture_cmd(stable_id, path), capture_output=True, timeout=5)
        if r.returncode == 0 and os.path.getsize(path) > 0:
            return path
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    return None
