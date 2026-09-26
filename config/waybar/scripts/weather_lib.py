"""
Weather for any timezone, shared by the world clock and the calendar popups.

Where: the timezone database knows a spot for each zone (usually its main city);
       a place can also be any city picked by name ("geo:lat,lon", see search()).
       The calendar shows the city chosen in ~/.config/waybar/weather-place.json.
What:  Open-Meteo (free, no key). One request covers every place at once, and
       answers are cached for 15 minutes in ~/.cache/worldclock/weather.json,
       so popups open with the last known weather straight away.
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")),
                     "worldclock", "weather.json")
MAX_AGE = 15 * 60
API = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → (day icon, night icon, words); icons are Nerd Font "weather-*"
_CLEAR = ("\U000f0599", "\U000f0594")
_PART = ("\U000f0595", "\U000f0f31")
_CLOUD = ("\U000f0590", "\U000f0590")
_FOG = ("\U000f0591", "\U000f0591")
_DRIZZLE = ("\U000f0597", "\U000f0597")
_RAIN = ("\U000f0596", "\U000f0596")
_SNOW = ("\U000f0598", "\U000f0598")
_STORM = ("\U000f0593", "\U000f0593")
CODES = {
    0: (_CLEAR, "Clear"), 1: (_PART, "Mostly clear"), 2: (_PART, "Partly cloudy"), 3: (_CLOUD, "Cloudy"),
    45: (_FOG, "Fog"), 48: (_FOG, "Icy fog"),
    51: (_DRIZZLE, "Light drizzle"), 53: (_DRIZZLE, "Drizzle"), 55: (_DRIZZLE, "Heavy drizzle"),
    56: (_DRIZZLE, "Freezing drizzle"), 57: (_DRIZZLE, "Freezing drizzle"),
    61: (_RAIN, "Light rain"), 63: (_RAIN, "Rain"), 65: (_RAIN, "Heavy rain"),
    66: (_RAIN, "Freezing rain"), 67: (_RAIN, "Freezing rain"),
    71: (_SNOW, "Light snow"), 73: (_SNOW, "Snow"), 75: (_SNOW, "Heavy snow"), 77: (_SNOW, "Snow grains"),
    80: (_RAIN, "Showers"), 81: (_RAIN, "Showers"), 82: (_RAIN, "Heavy showers"),
    85: (_SNOW, "Snow showers"), 86: (_SNOW, "Snow showers"),
    95: (_STORM, "Thunderstorm"), 96: (_STORM, "Thunderstorm, hail"), 99: (_STORM, "Thunderstorm, hail"),
}


def describe(code, is_day=True):
    """(icon, words) for a WMO weather code."""
    (day, night), words = CODES.get(int(code), (_CLOUD, "—"))
    return (day if is_day else night), words


def _coord(text):
    """ISO 6709 piece like +4241 or -0734512 → degrees."""
    sign = -1 if text[0] == "-" else 1
    digits = text[1:]
    deg_len = 2 if len(digits) in (4, 6) else 3
    deg, rest = int(digits[:deg_len]), digits[deg_len:]
    minutes = int(rest[:2])
    seconds = int(rest[2:4]) if len(rest) >= 4 else 0
    return sign * (deg + minutes / 60 + seconds / 3600)


def _load_places():
    places = {}
    for name in ("zone.tab", "zone1970.tab"):
        try:
            with open(f"/usr/share/zoneinfo/{name}") as f:
                for line in f:
                    if line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) < 3:
                        continue
                    m = re.match(r"^([+-]\d+)([+-]\d+)$", parts[1])
                    if m:
                        places[parts[2].strip()] = (round(_coord(m.group(1)), 3), round(_coord(m.group(2)), 3))
        except OSError:
            pass
    return places


PLACES = _load_places()


def place(zone):
    """(lat, lon) for a timezone or a "geo:lat,lon" key, or None (e.g. UTC)."""
    if zone.startswith("geo:"):
        try:
            lat, lon = zone[4:].split(",")
            return float(lat), float(lon)
        except ValueError:
            return None
    return PLACES.get(zone)


HOME_FILE = os.path.expanduser("~/.config/waybar/weather-place.json")
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"


def search(name, count=6):
    """Cities matching a name: [{"key": "geo:lat,lon", "name", "sub"}]."""
    query = urllib.parse.urlencode({"name": name, "count": count, "language": "en", "format": "json"})
    try:
        with urllib.request.urlopen(f"{GEOCODE}?{query}", timeout=8) as r:
            results = json.load(r).get("results") or []
    except (OSError, ValueError):
        return None      # offline
    out = []
    for c in results:
        sub = ", ".join(x for x in (c.get("admin1"), c.get("country")) if x and x != c.get("name"))
        out.append({"key": f"geo:{round(c['latitude'], 3)},{round(c['longitude'], 3)}",
                    "name": c.get("name", "?"), "sub": sub})
    return out


def get_home(default_zone):
    """The city the calendar shows weather for; the given timezone if none was chosen."""
    try:
        with open(HOME_FILE) as f:
            h = json.load(f)
        if place(h["key"]):
            return h
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"key": default_zone, "name": default_zone.rsplit("/", 1)[-1].replace("_", " "), "sub": ""}


def set_home(h):
    try:
        tmp = HOME_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"key": h["key"], "name": h["name"], "sub": h.get("sub", "")}, f)
        os.replace(tmp, HOME_FILE)
    except OSError:
        pass


def _read_cache():
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def cached(zone):
    """Last known weather for a zone (may be old), without touching the network."""
    return _read_cache().get(zone)


def fetch(zones, days=5):
    """Weather for every zone that has a place; fresh answers are fetched in one request.
    Returns {zone: {"temp", "code", "is_day", "daily": [{"date","code","max","min"}...], "at"}}."""
    cache = _read_cache()
    now = time.time()
    want = [z for z in dict.fromkeys(zones) if place(z)]
    stale = [z for z in want if now - cache.get(z, {}).get("at", 0) > MAX_AGE]
    if stale:
        lats = ",".join(str(place(z)[0]) for z in stale)
        lons = ",".join(str(place(z)[1]) for z in stale)
        query = urllib.parse.urlencode({
            "latitude": lats, "longitude": lons, "timezone": "auto", "forecast_days": days,
            "current": "temperature_2m,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        })
        try:
            with urllib.request.urlopen(f"{API}?{query}", timeout=8) as r:
                data = json.load(r)
            if isinstance(data, dict):
                data = [data]
            for z, d in zip(stale, data):
                cur, daily = d.get("current", {}), d.get("daily", {})
                cache[z] = {
                    "temp": cur.get("temperature_2m"), "code": cur.get("weather_code", 3),
                    "is_day": bool(cur.get("is_day", 1)), "at": now,
                    "daily": [{"date": t, "code": c, "max": hi, "min": lo} for t, c, hi, lo in zip(
                        daily.get("time", []), daily.get("weather_code", []),
                        daily.get("temperature_2m_max", []), daily.get("temperature_2m_min", []))],
                }
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(cache, f)
            os.replace(tmp, CACHE)
        except (OSError, ValueError):
            pass            # offline: keep showing the last known weather
    return {z: cache[z] for z in want if z in cache}


def deg(value):
    return "–" if value is None else f"{round(value)}°"
