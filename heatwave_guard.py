
"""
import csv
import json
import queue
import random
import re
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# =====================================================================================
# 1. DATABASE
# =====================================================================================
DB_PATH = Path(__file__).with_name("heatwave.db")

# (city, state, normal maximum temperature in deg C for the season)
CITIES = [
    ("Delhi", "Delhi", 39.0), ("Nagpur", "Maharashtra", 37.0),
    ("Jaipur", "Rajasthan", 39.5), ("Ahmedabad", "Gujarat", 39.5),
    ("Mumbai", "Maharashtra", 33.0), ("Hyderabad", "Telangana", 37.0),
    ("Chennai", "Tamil Nadu", 36.0), ("Bengaluru", "Karnataka", 34.0),
]
COORDS = {
    "Delhi": (28.61, 77.21), "Nagpur": (21.15, 79.09), "Jaipur": (26.91, 75.79),
    "Ahmedabad": (23.02, 72.57), "Mumbai": (19.08, 72.88), "Hyderabad": (17.39, 78.49),
    "Chennai": (13.08, 80.27), "Bengaluru": (12.97, 77.59),
}


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the tables; fill with simulated demo data on the very first run."""
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, state TEXT, normal_max REAL NOT NULL,
            latitude REAL, longitude REAL);
        CREATE TABLE IF NOT EXISTS readings(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL REFERENCES cities(id),
            day TEXT NOT NULL, max_temp REAL NOT NULL, min_temp REAL NOT NULL,
            humidity REAL NOT NULL, UNIQUE(city_id, day));
        CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL REFERENCES cities(id),
            day TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        cols = [r[1] for r in c.execute("PRAGMA table_info(cities)")]
        for col in ("latitude", "longitude"):          # upgrade older databases
            if col not in cols:
                c.execute(f"ALTER TABLE cities ADD COLUMN {col} REAL")
        if c.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 0:
            _seed(c)


def _seed(c, days=14):
    """Simulated demo readings: warming trend + noise, hotter for inland cities."""
    rnd = random.Random(42)
    today = date.today()
    for name, state, normal in CITIES:
        la, lo = COORDS[name]
        cid = c.execute("INSERT INTO cities(name,state,normal_max,latitude,longitude) VALUES(?,?,?,?,?)",
                        (name, state, normal, la, lo)).lastrowid
        inland = name in ("Delhi", "Nagpur", "Jaipur", "Ahmedabad")
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            warm = (0.45 if inland else 0.12) * i + rnd.uniform(-1.2, 1.2)
            tmax = round(normal - 1.5 + warm, 1)
            hum = round(rnd.uniform(25, 45) if inland else rnd.uniform(55, 80), 0)
            c.execute("INSERT INTO readings(city_id,day,max_temp,min_temp,humidity) VALUES(?,?,?,?,?)",
                      (cid, d.isoformat(), tmax, round(tmax - rnd.uniform(9, 14), 1), hum))


# ---- cities
def get_cities():
    with connect() as c:
        return c.execute("SELECT * FROM cities ORDER BY name").fetchall()


def get_city(city_id):
    with connect() as c:
        return c.execute("SELECT * FROM cities WHERE id=?", (city_id,)).fetchone()


def add_city(name, state, normal_max, lat=None, lon=None):
    with connect() as c:
        return c.execute("INSERT INTO cities(name,state,normal_max,latitude,longitude) VALUES(?,?,?,?,?)",
                         (name, state, normal_max, lat, lon)).lastrowid


def update_city(city_id, name, state, normal_max, lat=None, lon=None):
    with connect() as c:
        c.execute("UPDATE cities SET name=?, state=?, normal_max=?, latitude=?, longitude=? WHERE id=?",
                  (name, state, normal_max, lat, lon, city_id))


def set_city_coords(city_id, lat, lon):
    with connect() as c:
        c.execute("UPDATE cities SET latitude=?, longitude=? WHERE id=?", (lat, lon, city_id))


def delete_city(city_id):
    with connect() as c:
        c.execute("DELETE FROM readings WHERE city_id=?", (city_id,))
        c.execute("DELETE FROM alerts WHERE city_id=?", (city_id,))
        c.execute("DELETE FROM cities WHERE id=?", (city_id,))


def city_reading_counts():
    with connect() as c:
        return {r[0]: r[1] for r in c.execute("SELECT city_id, COUNT(*) FROM readings GROUP BY city_id")}


# ---- readings
_UPSERT = """INSERT INTO readings(city_id,day,max_temp,min_temp,humidity) VALUES(?,?,?,?,?)
            ON CONFLICT(city_id,day) DO UPDATE SET max_temp=excluded.max_temp,
            min_temp=excluded.min_temp, humidity=excluded.humidity"""


def add_reading(city_id, day, max_temp, min_temp, humidity):
    """Insert a reading (same city + day is replaced)."""
    with connect() as c:
        c.execute(_UPSERT, (city_id, day, max_temp, min_temp, humidity))


def bulk_add_readings(rows):
    """rows: iterable of (city_id, day, max, min, humidity). One transaction. Returns count."""
    rows = list(rows)
    with connect() as c:
        c.executemany(_UPSERT, rows)
    return len(rows)


def get_reading(reading_id):
    with connect() as c:
        return c.execute("""SELECT r.*, c.name city FROM readings r JOIN cities c ON c.id=r.city_id
                            WHERE r.id=?""", (reading_id,)).fetchone()


def get_readings(city_id=None, limit=3000):
    with connect() as c:
        return c.execute("""SELECT r.id, r.city_id, c.name city, c.normal_max, r.day,
               r.max_temp, r.min_temp, r.humidity FROM readings r JOIN cities c ON c.id=r.city_id
               WHERE (? IS NULL OR r.city_id=?) ORDER BY r.day DESC, c.name LIMIT ?""",
                         (city_id, city_id, limit)).fetchall()


def get_history(city_id, limit=14):
    """Last `limit` readings of a city, oldest first."""
    with connect() as c:
        rows = c.execute("SELECT * FROM readings WHERE city_id=? ORDER BY day DESC LIMIT ?",
                         (city_id, limit)).fetchall()
    return list(reversed(rows))


def update_reading(reading_id, day, max_temp, min_temp, humidity):
    with connect() as c:
        c.execute("UPDATE readings SET day=?, max_temp=?, min_temp=?, humidity=? WHERE id=?",
                  (day, max_temp, min_temp, humidity, reading_id))


def delete_reading(reading_id):
    with connect() as c:
        c.execute("DELETE FROM readings WHERE id=?", (reading_id,))


def latest_per_city():
    with connect() as c:
        return c.execute("""SELECT c.id city_id, c.name, c.state, c.normal_max,
               r.day, r.max_temp, r.min_temp, r.humidity FROM cities c
               JOIN readings r ON r.city_id=c.id
               WHERE r.day=(SELECT MAX(day) FROM readings WHERE city_id=c.id)
               ORDER BY c.name""").fetchall()


# ---- alerts
def save_alert(city_id, day, level, message):
    with connect() as c:
        c.execute("INSERT INTO alerts(city_id,day,level,message) VALUES(?,?,?,?)",
                  (city_id, day, level, message))


def get_alerts(limit=100):
    with connect() as c:
        return c.execute("""SELECT a.id, c.name city, a.day, a.level, a.message, a.created_at
               FROM alerts a JOIN cities c ON c.id=a.city_id ORDER BY a.id DESC LIMIT ?""",
                         (limit,)).fetchall()


def delete_alert(alert_id):
    with connect() as c:
        c.execute("DELETE FROM alerts WHERE id=?", (alert_id,))


# =====================================================================================
# 2. PREDICTOR  (all calculations)
# =====================================================================================
LEVELS = ["Normal", "Caution", "Heatwave", "Severe Heatwave"]
COLORS = {"Normal": "#2e9e5b", "Caution": "#e6b800", "Heatwave": "#ec7a1c", "Severe Heatwave": "#d62828"}
ADVICE = {
    "Normal": "No action needed. Stay hydrated as usual.",
    "Caution": "Hot conditions. Avoid strenuous outdoor work at noon; drink water often.",
    "Heatwave": "Heatwave conditions. Avoid going out 12-4 PM, protect children, elderly and "
                "outdoor workers, open cooling shelters.",
    "Severe Heatwave": "SEVERE heatwave. Stay indoors, activate emergency health response, issue "
                       "public alert and arrange water/ORS distribution.",
}


def heat_index(temp_c, humidity):
    """Apparent temperature (deg C) using the NWS Rothfusz regression."""
    t = temp_c * 9 / 5 + 32
    if t < 80:
        return round(temp_c, 1)
    r = humidity
    hi = (-42.379 + 2.04901523 * t + 10.14333127 * r - 0.22475541 * t * r
          - 6.83783e-3 * t * t - 5.481717e-2 * r * r + 1.22874e-3 * t * t * r
          + 8.5282e-4 * t * r * r - 1.99e-6 * t * t * r * r)
    if r < 13 and 80 <= t <= 112:
        hi -= ((13 - r) / 4) * ((17 - abs(t - 95)) / 17) ** 0.5
    elif r > 85 and 80 <= t <= 87:
        hi += ((r - 85) / 10) * ((87 - t) / 5)
    return round((hi - 32) * 5 / 9, 1)


def classify(max_temp, normal_max, humidity):
    """IMD-style rule on departure from normal, plus a heat-index check."""
    dep = max_temp - normal_max
    if max_temp >= 47 or dep >= 6.5:
        level = 3
    elif max_temp >= 40 and dep >= 4.5:
        level = 2
    elif max_temp >= 37 and dep >= 2.0:
        level = 1
    else:
        level = 0
    hi = heat_index(max_temp, humidity)          # secondary check: humid heat feels hotter
    if hi >= 54 and max_temp >= 37:
        level = max(level, 2)
    elif hi >= 41:
        level = max(level, 1)
    return LEVELS[level]


def linear_fit(ys):
    """Least-squares line y = a + b*x for x = 0..n-1. Returns (a, b)."""
    n = len(ys)
    if n < 2:
        return (ys[0] if ys else 0.0), 0.0
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((i - mx) ** 2 for i in range(n))
    b = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sxx
    return my - b * mx, b


def make_forecast(history, normal_max, days=3):
    """Forecast the next `days`: linear trend of the last 7 max temps, mean humidity of the window."""
    window = history[-7:]
    temps = [r["max_temp"] for r in window]
    hum = sum(r["humidity"] for r in window) / len(window)
    a, b = linear_fit(temps)
    last_day = date.fromisoformat(window[-1]["day"])
    out = []
    for k in range(1, days + 1):
        t = round(a + b * (len(temps) - 1 + k), 1)
        out.append({"day": (last_day + timedelta(days=k)).isoformat(), "max_temp": t,
                    "humidity": round(hum), "heat_index": heat_index(t, hum),
                    "level": classify(t, normal_max, hum)})
    return out, b


def early_warning(city, rows):
    """Worst level in the forecast -> (level, message) for the alert log."""
    worst = max(rows, key=lambda f: LEVELS.index(f["level"]))
    if LEVELS.index(worst["level"]) == 0:
        return "Normal", f"{city}: no heatwave expected in the next {len(rows)} days."
    return worst["level"], (f"{city}: {worst['level']} likely on {worst['day']} "
                            f"(max {worst['max_temp']} C, heat index {worst['heat_index']} C). "
                            + ADVICE[worst["level"]])


def validate_reading(day_s, tmax_s, tmin_s, hum_s):
    """Check one observation typed by the user -> (day, tmax, tmin, hum) or ValueError."""
    try:
        day = date.fromisoformat(str(day_s).strip()).isoformat()
    except ValueError:
        raise ValueError("Date must look like 2026-05-21 (YYYY-MM-DD).")
    try:
        tmax, tmin, hum = float(tmax_s), float(tmin_s), float(hum_s)
    except ValueError:
        raise ValueError("Max temp, min temp and humidity must be numbers.")
    if not (-10 <= tmin <= tmax <= 60):
        raise ValueError("Temperatures must satisfy -10 <= min <= max <= 60 \u00b0C.")
    if not (0 <= hum <= 100):
        raise ValueError("Humidity must be between 0 and 100 %.")
    return day, tmax, tmin, hum


# =====================================================================================
# 3. IMPORTER  (CSV from Kaggle / any source, and Open-Meteo online data)
# =====================================================================================
NONE = "(none)"
_ISO = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
_DAYFIRST = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y"]
_MONFIRST = ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y", "%b %d, %Y", "%B %d, %Y"]


def parse_day(text, dayfirst=True):
    """Turn many date styles into YYYY-MM-DD (None if unreadable). Ignores a time part."""
    s = re.sub(r"[T ]\d{1,2}:\d{2}.*$", "", str(text).strip())
    for fmt in _ISO + (_DAYFIRST + _MONFIRST if dayfirst else _MONFIRST + _DAYFIRST):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _num(text):
    """Forgiving float parser: '36.5', '36,5', '36.5 C', '45%', 'NA' -> float or None."""
    s = str(text).strip()
    if s.lower() in ("", "na", "n/a", "nan", "null", "none", "-", "--"):
        return None
    s = re.sub(r"\s*(\u00b0|deg)?\s*[CFK%]$", "", s, flags=re.I)
    if "," in s:
        s = s.replace(",", ".") if s.count(",") == 1 and "." not in s else s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _open_csv(path):
    """Open a CSV with an auto-detected delimiter. Returns (file, DictReader)."""
    f = open(path, newline="", encoding="utf-8-sig", errors="replace")
    sample = f.read(8192)
    f.seek(0)
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delim = ","
    return f, csv.DictReader(f, delimiter=delim)


def preview_csv(path, n=3):
    f, rd = _open_csv(path)
    with f:
        headers = [h.strip() for h in (rd.fieldnames or []) if h is not None]
        rows = []
        for row in rd:
            rows.append({k: v for k, v in row.items() if k is not None})
            if len(rows) >= n:
                break
    return headers, rows


def guess_mapping(headers):
    """Guess which CSV column is which, from common Kaggle-style header names."""
    norm = {h: re.sub(r"[^a-z0-9]", "", h.lower()) for h in headers}
    used = set()

    def find(words, bad=()):
        for h, n in norm.items():
            if h not in used and any(w in n for w in words) and not any(b in n for b in bad):
                used.add(h)
                return h
        return None
    m = {}
    m["tmax"] = find(["tmax", "maxtemp", "tempmax", "temperaturemax", "maximumtemp", "maxtemperature",
                      "temperature2mmax", "hightemp", "tmaxc"])
    m["tmin"] = find(["tmin", "mintemp", "tempmin", "temperaturemin", "minimumtemp", "mintemperature",
                      "temperature2mmin", "lowtemp", "tminc"])
    m["hum"] = find(["humid", "relativehum", "rhmean", "rh"])
    m["day"] = find(["date", "datetime", "day", "time", "dt"], bad=["max", "min"])
    m["city"] = find(["city", "station", "location", "place", "district", "town", "name"])
    m["temp"] = None if m["tmax"] else find(["temperature", "temp", "tavg", "avgtemp", "tmean"])
    return m


class ImportResult:
    def __init__(self):
        self.records = {}          # (city, 'YYYY-MM-DD') -> {'max','min','hum'}
        self.skipped = {}          # reason -> count
        self.estimated_min = 0
        self.defaulted_hum = 0


def parse_csv(path, mapping, unit="C", dayfirst=True, target_city=None, default_hum=50.0):
    """Read a CSV into daily records. Hourly files are collapsed to one row per city/day
    (max of the day, min of the day, mean humidity)."""
    if not mapping.get("day"):
        raise ValueError("Choose the Date column.")
    if not (mapping.get("tmax") or mapping.get("temp")):
        raise ValueError("Choose a 'Max temp' column, or a 'Single temp' column.")
    conv = {"C": lambda x: x, "F": lambda x: (x - 32) * 5 / 9, "K": lambda x: x - 273.15}[unit]
    res = ImportResult()
    acc = defaultdict(lambda: {"mx": [], "mn": [], "t": [], "h": []})
    names = {}                                   # lower-case city -> first spelling seen

    def skip(why):
        res.skipped[why] = res.skipped.get(why, 0) + 1

    f, rd = _open_csv(path)
    with f:
        for row in rd:
            day = parse_day(row.get(mapping["day"]) or "", dayfirst)
            if not day:
                skip("bad date")
                continue
            city = (target_city if not mapping.get("city") else (row.get(mapping["city"]) or "")).strip()
            if not city:
                skip("no city")
                continue
            vals = {}
            for key in ("tmax", "tmin", "temp"):
                col = mapping.get(key)
                v = _num(row.get(col)) if col else None
                vals[key] = None if v is None else conv(v)
            got = [v for v in vals.values() if v is not None]
            if not got:
                skip("missing temperature")
                continue
            if any(not -10 <= v <= 60 for v in got):
                skip("temperature out of range")
                continue
            key = (names.setdefault(city.lower(), city), day)
            a = acc[key]
            if vals["tmax"] is not None:
                a["mx"].append(vals["tmax"])
            if vals["tmin"] is not None:
                a["mn"].append(vals["tmin"])
            if vals["temp"] is not None:
                a["t"].append(vals["temp"])
            h = _num(row.get(mapping["hum"])) if mapping.get("hum") else None
            if h is not None and 0 <= h <= 100:
                a["h"].append(h)

    for key, a in acc.items():
        if not a["mx"] and not a["t"]:
            skip("no max temperature")
            continue
        mx = max(a["mx"]) if a["mx"] else max(a["t"])
        if a["mn"]:
            mn = min(a["mn"])
        elif len(a["t"]) > 1:
            mn = min(a["t"])
        else:
            mn = mx - 12
            res.estimated_min += 1
        mn = min(mn, mx)
        if a["h"]:
            hum = sum(a["h"]) / len(a["h"])
        else:
            hum = default_hum
            res.defaulted_hum += 1
        res.records[key] = {"max": round(mx, 1), "min": round(mn, 1), "hum": round(hum)}
    return res


def _get_json(url, params):
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params),
                                 headers={"User-Agent": "HeatwaveGuard/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def geocode(name):
    """Find coordinates of a place name (Open-Meteo geocoding). -> [(label, lat, lon), ...]"""
    data = _get_json("https://geocoding-api.open-meteo.com/v1/search",
                     {"name": name, "count": 5, "language": "en", "format": "json"})
    out = []
    for r in data.get("results") or []:
        label = ", ".join(p for p in (r.get("name"), r.get("admin1"), r.get("country")) if p)
        out.append((label, r["latitude"], r["longitude"]))
    return out


def fetch_open_meteo(lat, lon, days, default_hum=50.0):
    """Download daily max/min temperature and mean humidity for the last `days` days.
    -> (rows[(day, max, min, hum)], info)"""
    today = date.today()
    if days <= 90:                                # recent data up to yesterday
        url = "https://api.open-meteo.com/v1/forecast"
        end = today - timedelta(days=1)
        extra = {"past_days": days + 1, "forecast_days": 1}
    else:                                         # long history (archive lags a few days)
        url = "https://archive-api.open-meteo.com/v1/archive"
        end = today - timedelta(days=3)
        extra = {"start_date": (end - timedelta(days=days - 1)).isoformat(), "end_date": end.isoformat()}
    start = end - timedelta(days=days - 1)
    base = {"latitude": lat, "longitude": lon, "timezone": "auto", **extra}
    try:
        data = _get_json(url, {**base, "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean"})
    except urllib.error.HTTPError:                # retry without humidity, use the default instead
        data = _get_json(url, {**base, "daily": "temperature_2m_max,temperature_2m_min"})
    d = data.get("daily") or {}
    rows, no_hum = [], 0
    rh_list = d.get("relative_humidity_2m_mean") or [None] * len(d.get("time", []))
    for day, mx, mn, rh in zip(d.get("time", []), d.get("temperature_2m_max", []),
                               d.get("temperature_2m_min", []), rh_list):
        if mx is None or mn is None or not (start.isoformat() <= day <= end.isoformat()):
            continue
        if rh is None:
            rh, no_hum = default_hum, no_hum + 1
        rows.append((day, round(mx, 1), round(mn, 1), round(rh)))
    return rows, {"start": rows[0][0] if rows else "", "end": rows[-1][0] if rows else "", "no_humidity": no_hum}


# =====================================================================================
# 4. GUI  (Tkinter)
# =====================================================================================
BG, CARD, INK, ACCENT, MUTED = "#0f1b2d", "#17283f", "#eef3fa", "#ff8a3d", "#9fb3cf"


class ReadingDialog(tk.Toplevel):
    """Pop-up form to edit one stored reading."""

    def __init__(self, parent, row, on_save):
        super().__init__(parent)
        self.on_save = on_save
        self.title(f"Edit reading - {row['city']}")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        f = ttk.Frame(self)
        f.pack(padx=25, pady=20)
        self.vars = [tk.StringVar(value=str(row[k])) for k in ("day", "max_temp", "min_temp", "humidity")]
        labels = ("Date (YYYY-MM-DD)", "Max temperature (\u00b0C)", "Min temperature (\u00b0C)", "Relative humidity (%)")
        for i, (lab, v) in enumerate(zip(labels, self.vars)):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 18))
            ttk.Entry(f, textvariable=v, width=22).grid(row=i, column=1, sticky="w")
        bt = ttk.Frame(f)
        bt.grid(row=4, column=0, columnspan=2, pady=(14, 0), sticky="e")
        ttk.Button(bt, text="Cancel", command=self.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(bt, text="Save changes", style="Accent.TButton", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.grab_set()

    def _ok(self):
        try:
            vals = validate_reading(*(v.get() for v in self.vars))
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e), parent=self)
            return
        try:
            self.on_save(*vals)
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate date", "This city already has a reading for that date.", parent=self)
            return
        self.destroy()


class HeatwaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Heatwave Guard - Climate Intelligence for Heatwave Monitoring")
        self.geometry("1040x700")
        self.minsize(920, 620)
        self.configure(bg=BG)
        init_db()
        self.city_boxes = []          # (combobox, variable, fixed first entries) kept in sync with the DB
        self.fc = None
        self._load_cities()
        self._style()
        self._header()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        tabs = [("tab_dash", "Dashboard"), ("tab_add", "Add Reading"), ("tab_data", "Data (Edit)"),
                ("tab_imp", "Import Data"), ("tab_city", "Cities"), ("tab_fc", "Forecast & Warning"),
                ("tab_alerts", "Alert Log")]
        for attr, label in tabs:
            setattr(self, attr, ttk.Frame(nb))
            nb.add(getattr(self, attr), text=f"  {label}  ")
        self._build_dashboard()
        self._build_add()
        self._build_data()
        self._build_import()
        self._build_cities()
        self._build_forecast()
        self._build_alerts()
        self.refresh_all()

    # ---------- shared helpers ----------
    def _load_cities(self):
        self.city_rows = {c["name"]: c for c in get_cities()}
        self.cities = {n: c["id"] for n, c in self.city_rows.items()}

    def _register_box(self, combo, var, first=()):
        self.city_boxes.append((combo, var, list(first)))

    def reload_cities(self):
        self._load_cities()
        names = list(self.cities)
        for combo, var, first in self.city_boxes:
            combo["values"] = first + names
            if var.get() not in first + names:
                var.set((first + names)[0])

    def _run_bg(self, work, done):
        """Run work() in a thread (network / big files); call done(ok, value) on the GUI thread."""
        q = queue.Queue()

        def target():
            try:
                q.put((True, work()))
            except Exception as e:  # noqa: BLE001 - shown to the user
                q.put((False, e))
        threading.Thread(target=target, daemon=True).start()

        def poll():
            try:
                ok, val = q.get_nowait()
            except queue.Empty:
                self.after(100, poll)
                return
            done(ok, val)
        poll()

    @staticmethod
    def _net_error(e):
        if isinstance(e, (urllib.error.URLError, TimeoutError, OSError)):
            return "Could not reach the internet / Open-Meteo. Check your connection and try again."
        return str(e)

    # ---------- look & feel ----------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        s.configure("H.TLabel", font=("Segoe UI", 13, "bold"))
        s.configure("Muted.TLabel", foreground=MUTED, font=("Segoe UI", 9))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=INK, padding=(6, 8), font=("Segoe UI", 10, "bold"))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#101010")])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=28, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background="#22385a", foreground=INK, font=("Segoe UI", 10, "bold"))
        s.configure("Accent.TButton", background=ACCENT, foreground="#101010", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Accent.TButton", background=[("active", "#ffa05f")])
        s.configure("TButton", font=("Segoe UI", 10), padding=6)
        s.configure("TLabelframe", background=BG, bordercolor="#26405f")
        s.configure("TLabelframe.Label", background=BG, foreground=ACCENT, font=("Segoe UI", 11, "bold"))

    def _header(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=16, pady=12)
        tk.Label(f, text="\u2600  Heatwave Guard", bg=BG, fg=ACCENT, font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(f, text="Monitoring  \u2022  Prediction  \u2022  Early Warning", bg=BG, fg=MUTED,
                 font=("Segoe UI", 11)).pack(side="left", padx=18, pady=(8, 0))

    def _table(self, parent, cols, widths=None, height=None, selectmode="browse", pack=True):
        """Create a scrollable Treeview with level colour tags."""
        wrap = ttk.Frame(parent)
        kw = {"height": height} if height else {}
        tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode=selectmode, **kw)
        for i, c in enumerate(cols):
            tree.heading(c, text=c)
            tree.column(c, width=(widths[i] if widths else 110), anchor="center")
        for lvl, col in COLORS.items():
            tree.tag_configure(lvl, foreground=col)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return wrap, tree

    # ---------- dashboard ----------
    def _build_dashboard(self):
        top = ttk.Frame(self.tab_dash)
        top.pack(fill="x", padx=10, pady=10)
        self.cards = {}
        for lvl in LEVELS:
            c = tk.Frame(top, bg=CARD, highlightthickness=2, highlightbackground=COLORS[lvl])
            c.pack(side="left", expand=True, fill="x", padx=5)
            n = tk.Label(c, text="0", bg=CARD, fg=COLORS[lvl], font=("Segoe UI", 26, "bold"))
            n.pack(pady=(6, 0))
            tk.Label(c, text=lvl, bg=CARD, fg=INK, font=("Segoe UI", 10)).pack(pady=(0, 6))
            self.cards[lvl] = n
        cols = ("City", "State", "Date", "Max \u00b0C", "Normal \u00b0C", "Humidity %", "Heat Index \u00b0C", "Status")
        wrap, self.tree = self._table(self.tab_dash, cols, height=7)
        wrap.pack(fill="x", padx=15)
        ttk.Label(self.tab_dash, text="Latest maximum temperature by city (red line = city normal)",
                  style="H.TLabel").pack(anchor="w", padx=15, pady=(12, 2))
        self.bar_canvas = tk.Canvas(self.tab_dash, bg=CARD, height=210, highlightthickness=0)
        self.bar_canvas.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.bar_canvas.bind("<Configure>", lambda e: self._draw_bars())

    def _refresh_dashboard(self):
        self.tree.delete(*self.tree.get_children())
        self.latest = latest_per_city()
        counts = dict.fromkeys(LEVELS, 0)
        for r in self.latest:
            lvl = classify(r["max_temp"], r["normal_max"], r["humidity"])
            counts[lvl] += 1
            self.tree.insert("", "end", tags=(lvl,), values=(
                r["name"], r["state"] or "", r["day"], r["max_temp"], r["normal_max"], int(r["humidity"]),
                heat_index(r["max_temp"], r["humidity"]), lvl))
        for lvl, n in counts.items():
            self.cards[lvl].config(text=str(n))
        self._draw_bars()

    def _draw_bars(self):
        cv = self.bar_canvas
        cv.delete("all")
        rows = getattr(self, "latest", [])
        if not rows:
            return
        w, h = cv.winfo_width(), cv.winfo_height()
        left, bottom, top = 40, h - 30, 15
        vmax = max(max(r["max_temp"], r["normal_max"]) for r in rows) + 3
        scale = (bottom - top) / vmax
        slot = (w - left - 10) / len(rows)
        for t in range(0, int(vmax) + 1, 10):
            y = bottom - t * scale
            cv.create_line(left, y, w - 10, y, fill="#26405f")
            cv.create_text(left - 6, y, text=str(t), fill=MUTED, anchor="e", font=("Segoe UI", 8))
        for i, r in enumerate(rows):
            lvl = classify(r["max_temp"], r["normal_max"], r["humidity"])
            x0, x1 = left + i * slot + slot * 0.2, left + (i + 1) * slot - slot * 0.2
            y = bottom - r["max_temp"] * scale
            cv.create_rectangle(x0, y, x1, bottom, fill=COLORS[lvl], outline="")
            cv.create_text((x0 + x1) / 2, y - 8, text=f'{r["max_temp"]}', fill=INK, font=("Segoe UI", 9, "bold"))
            cv.create_text((x0 + x1) / 2, bottom + 12, text=r["name"][:10], fill=INK, font=("Segoe UI", 9))
            yn = bottom - r["normal_max"] * scale
            cv.create_line(x0 - 6, yn, x1 + 6, yn, fill="#ff4d4d", width=2)

    # ---------- add reading ----------
    def _build_add(self):
        f = ttk.Frame(self.tab_add)
        f.pack(padx=30, pady=25, anchor="nw")
        ttk.Label(f, text="Record a daily weather observation", style="H.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))
        self.v_city = tk.StringVar(value=next(iter(self.cities)))
        self.v_day = tk.StringVar(value=date.today().isoformat())
        self.v_max, self.v_min, self.v_hum = tk.StringVar(), tk.StringVar(), tk.StringVar()
        city_cb = ttk.Combobox(f, textvariable=self.v_city, values=list(self.cities), state="readonly", width=28)
        self._register_box(city_cb, self.v_city)
        fields = [("City", city_cb),
                  ("Date (YYYY-MM-DD)", ttk.Entry(f, textvariable=self.v_day, width=30)),
                  ("Max temperature (\u00b0C)", ttk.Entry(f, textvariable=self.v_max, width=30)),
                  ("Min temperature (\u00b0C)", ttk.Entry(f, textvariable=self.v_min, width=30)),
                  ("Relative humidity (%)", ttk.Entry(f, textvariable=self.v_hum, width=30))]
        for i, (lab, w) in enumerate(fields, start=1):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=7, padx=(0, 20))
            w.grid(row=i, column=1, sticky="w")
        ttk.Button(f, text="Save Reading", style="Accent.TButton", command=self._save_reading).grid(
            row=7, column=1, sticky="w", pady=18)
        self.add_msg = ttk.Label(f, text="")
        self.add_msg.grid(row=8, column=0, columnspan=2, sticky="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=520, justify="left",
                  text="Saving a reading for a city + date that already exists replaces it. To fix or remove old "
                       "readings use the 'Data (Edit)' tab; to load many at once use 'Import Data'.").grid(
            row=9, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _save_reading(self):
        try:
            day, tmax, tmin, hum = validate_reading(self.v_day.get(), self.v_max.get(), self.v_min.get(), self.v_hum.get())
        except ValueError as e:
            messagebox.showerror("Invalid input", f"Please check the values.\n\n{e}")
            return
        city = self.v_city.get()
        add_reading(self.cities[city], day, tmax, tmin, hum)
        lvl = classify(tmax, self.city_rows[city]["normal_max"], hum)
        self.add_msg.config(text=f"Saved. {city} on {day}: heat index {heat_index(tmax, hum)} \u00b0C, status {lvl}")
        self.v_max.set("")
        self.v_min.set("")
        self.v_hum.set("")
        self.refresh_all()

    # ---------- data table (view / edit / delete / export) ----------
    def _build_data(self):
        top = ttk.Frame(self.tab_data)
        top.pack(fill="x", padx=15, pady=(12, 6))
        ttk.Label(top, text="City:").pack(side="left")
        self.v_data_city = tk.StringVar(value="All cities")
        cb = ttk.Combobox(top, textvariable=self.v_data_city, values=["All cities"] + list(self.cities),
                          state="readonly", width=18)
        cb.pack(side="left", padx=8)
        self._register_box(cb, self.v_data_city, ["All cities"])
        cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_data())
        ttk.Button(top, text="Delete selected", command=self._delete_readings).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Export CSV", command=self._export_csv).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Select all", command=lambda: self.data_tree.selection_set(
            self.data_tree.get_children())).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Edit selected", style="Accent.TButton", command=self._edit_reading).pack(side="right")
        self.data_stats = tk.Label(self.tab_data, text="", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 10))
        self.data_stats.pack(fill="x", padx=15, pady=(0, 6))
        cols = ("City", "Date", "Max \u00b0C", "Min \u00b0C", "Humidity %", "Heat Index \u00b0C", "Status")
        wrap, self.data_tree = self._table(self.tab_data, cols, selectmode="extended")
        wrap.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.data_tree.bind("<Double-1>", lambda e: self._edit_reading())
        self.data_tree.bind("<Delete>", lambda e: self._delete_readings())

    def _refresh_data(self):
        name = self.v_data_city.get()
        cid = None if name == "All cities" else self.cities.get(name)
        limit = 3000
        rows = get_readings(cid, limit)
        self.data_tree.delete(*self.data_tree.get_children())
        heat_days, hottest = 0, None
        for r in rows:
            lvl = classify(r["max_temp"], r["normal_max"], r["humidity"])
            heat_days += lvl in ("Heatwave", "Severe Heatwave")
            if hottest is None or r["max_temp"] > hottest["max_temp"]:
                hottest = r
            self.data_tree.insert("", "end", iid=str(r["id"]), tags=(lvl,), values=(
                r["city"], r["day"], r["max_temp"], r["min_temp"], int(r["humidity"]),
                heat_index(r["max_temp"], r["humidity"]), lvl))
        if rows:
            avg = sum(r["max_temp"] for r in rows) / len(rows)
            more = f" (newest {limit} shown)" if len(rows) == limit else ""
            self.data_stats.config(text=f'{len(rows)} readings{more}   |   average max {avg:.1f} \u00b0C   |   '
                                        f'hottest {hottest["max_temp"]} \u00b0C ({hottest["city"]}, {hottest["day"]})'
                                        f'   |   heatwave-level days: {heat_days}')
        else:
            self.data_stats.config(text="No readings yet - add one, or use the Import Data tab.")

    def _edit_reading(self):
        sel = self.data_tree.selection()
        if not sel:
            messagebox.showinfo("Edit", "Select a reading in the table first.")
            return
        rid = int(sel[0])

        def save(day, tmax, tmin, hum):
            update_reading(rid, day, tmax, tmin, hum)
            self.refresh_all()
        ReadingDialog(self, get_reading(rid), save)

    def _delete_readings(self):
        sel = self.data_tree.selection()
        if sel and messagebox.askyesno("Delete", f"Delete {len(sel)} selected reading(s)? This cannot be undone."):
            for iid in sel:
                delete_reading(int(iid))
            self.refresh_all()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="heatwave_readings.csv",
                                            filetypes=[("CSV file", "*.csv")])
        if not path:
            return
        name = self.v_data_city.get()
        rows = get_readings(None if name == "All cities" else self.cities.get(name), 10 ** 7)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["city", "date", "max_temp", "min_temp", "humidity", "heat_index", "status"])
            for r in rows:
                w.writerow([r["city"], r["day"], r["max_temp"], r["min_temp"], r["humidity"],
                            heat_index(r["max_temp"], r["humidity"]),
                            classify(r["max_temp"], r["normal_max"], r["humidity"])])
        messagebox.showinfo("Export", f"Saved {len(rows)} readings to\n{path}")

    # ---------- import (CSV / Kaggle + online) ----------
    def _build_import(self):
        box = ttk.LabelFrame(self.tab_imp, text="  Import a CSV file (Kaggle or any weather dataset)  ")
        box.pack(fill="x", padx=15, pady=(12, 6))
        r0 = ttk.Frame(box)
        r0.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Button(r0, text="Choose CSV file...", style="Accent.TButton", command=self._pick_csv).pack(side="left")
        self.csv_path = ""
        self.csv_label = ttk.Label(r0, text="  no file chosen", style="Muted.TLabel")
        self.csv_label.pack(side="left")
        self.csv_preview = tk.Text(box, height=4, bg=CARD, fg=INK, relief="flat", font=("Courier", 9), wrap="none")
        self.csv_preview.pack(fill="x", padx=12, pady=4)
        self.csv_preview.config(state="disabled")

        grid = ttk.Frame(box)
        grid.pack(fill="x", padx=12, pady=4)
        self.imp_vars, self.imp_boxes = {}, {}
        spec = [("day", "Date column"), ("city", "City column"), ("tmax", "Max temp column"),
                ("tmin", "Min temp column"), ("temp", "Single temp column"), ("hum", "Humidity column")]
        for i, (key, lab) in enumerate(spec):
            r, c = divmod(i, 3)
            ttk.Label(grid, text=lab).grid(row=r * 2, column=c, sticky="w", padx=(0, 14))
            v = tk.StringVar(value=NONE)
            cb = ttk.Combobox(grid, textvariable=v, values=[NONE], state="readonly", width=22)
            cb.grid(row=r * 2 + 1, column=c, sticky="w", padx=(0, 14), pady=(0, 6))
            self.imp_vars[key], self.imp_boxes[key] = v, cb

        opt = ttk.Frame(box)
        opt.pack(fill="x", padx=12, pady=(2, 4))
        self.v_unit = tk.StringVar(value="Celsius")
        self.v_dayfirst = tk.StringVar(value="Day first (31/12/2024)")
        self.v_defhum = tk.StringVar(value="50")
        self.v_imp_city = tk.StringVar(value=next(iter(self.cities)))
        ttk.Label(opt, text="Temperature unit").grid(row=0, column=0, sticky="w", padx=(0, 14))
        ttk.Combobox(opt, textvariable=self.v_unit, values=["Celsius", "Fahrenheit", "Kelvin"],
                     state="readonly", width=12).grid(row=1, column=0, sticky="w", padx=(0, 14))
        ttk.Label(opt, text="Date order").grid(row=0, column=1, sticky="w", padx=(0, 14))
        ttk.Combobox(opt, textvariable=self.v_dayfirst, values=["Day first (31/12/2024)", "Month first (12/31/2024)"],
                     state="readonly", width=24).grid(row=1, column=1, sticky="w", padx=(0, 14))
        ttk.Label(opt, text="Humidity if missing (%)").grid(row=0, column=2, sticky="w", padx=(0, 14))
        ttk.Entry(opt, textvariable=self.v_defhum, width=8).grid(row=1, column=2, sticky="w", padx=(0, 14))
        ttk.Label(opt, text="City (if file has no city column)").grid(row=0, column=3, sticky="w")
        cb = ttk.Combobox(opt, textvariable=self.v_imp_city, values=list(self.cities), state="readonly", width=16)
        cb.grid(row=1, column=3, sticky="w")
        self._register_box(cb, self.v_imp_city)

        r3 = ttk.Frame(box)
        r3.pack(fill="x", padx=12, pady=(6, 10))
        self.btn_csv = ttk.Button(r3, text="Import into database", style="Accent.TButton", command=self._import_csv)
        self.btn_csv.pack(side="left")
        self.csv_msg = tk.Label(r3, text="", bg=BG, fg=INK, justify="left", wraplength=700, font=("Segoe UI", 10))
        self.csv_msg.pack(side="left", padx=14)

        net = ttk.LabelFrame(self.tab_imp, text="  Download real data online (Open-Meteo, free, no key)  ")
        net.pack(fill="x", padx=15, pady=(8, 6))
        r = ttk.Frame(net)
        r.pack(fill="x", padx=12, pady=10)
        self.v_net_city = tk.StringVar(value=next(iter(self.cities)))
        self.v_net_days = tk.StringVar(value="60")
        ttk.Label(r, text="City").pack(side="left")
        cb = ttk.Combobox(r, textvariable=self.v_net_city, values=list(self.cities), state="readonly", width=16)
        cb.pack(side="left", padx=(6, 16))
        self._register_box(cb, self.v_net_city)
        ttk.Label(r, text="Past days").pack(side="left")
        ttk.Spinbox(r, from_=7, to=730, textvariable=self.v_net_days, width=6).pack(side="left", padx=(6, 16))
        self.btn_net = ttk.Button(r, text="Download & import", style="Accent.TButton", command=self._download)
        self.btn_net.pack(side="left")
        self.net_msg = tk.Label(net, text="", bg=BG, fg=INK, justify="left", wraplength=900, anchor="w",
                                font=("Segoe UI", 10))
        self.net_msg.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(net, style="Muted.TLabel", wraplength=900, justify="left",
                  text="Needs internet. Uses the city's latitude/longitude (looked up automatically if empty). "
                       "Existing readings for the same dates are overwritten.").pack(anchor="w", padx=12, pady=(0, 10))

    def _pick_csv(self):
        path = filedialog.askopenfilename(title="Choose a weather CSV",
                                          filetypes=[("CSV / text files", "*.csv *.tsv *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            headers, rows = preview_csv(path)
            if not headers:
                raise ValueError("The file has no header row.")
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Cannot read file", str(e))
            return
        self.csv_path = path
        self.csv_label.config(text="  " + path)
        guess = guess_mapping(headers)
        for key, cb in self.imp_boxes.items():
            cb["values"] = [NONE] + headers
            self.imp_vars[key].set(guess[key] or NONE)
        self.csv_preview.config(state="normal")
        self.csv_preview.delete("1.0", "end")
        self.csv_preview.insert("end", " | ".join(headers) + "\n")
        for row in rows:
            self.csv_preview.insert("end", " | ".join(str(row.get(h, "")) for h in headers) + "\n")
        self.csv_preview.config(state="disabled")
        self.csv_msg.config(text="Columns were detected automatically - check them, then press Import.")

    def _default_humidity(self):
        try:
            hum = float(self.v_defhum.get())
            if not 0 <= hum <= 100:
                raise ValueError
            return hum
        except ValueError:
            messagebox.showerror("Invalid input", "'Humidity if missing' must be a number from 0 to 100.")
            return None

    def _import_csv(self):
        if not self.csv_path:
            messagebox.showinfo("Import", "Choose a CSV file first.")
            return
        hum = self._default_humidity()
        if hum is None:
            return
        mapping = {k: (None if v.get() == NONE else v.get()) for k, v in self.imp_vars.items()}
        unit = {"Celsius": "C", "Fahrenheit": "F", "Kelvin": "K"}[self.v_unit.get()]
        dayfirst = self.v_dayfirst.get().startswith("Day")
        target = None if mapping["city"] else self.v_imp_city.get()
        self.btn_csv.state(["disabled"])
        self.csv_msg.config(text="Reading file...")
        self._run_bg(lambda: parse_csv(self.csv_path, mapping, unit, dayfirst, target, hum), self._csv_parsed)

    def _csv_parsed(self, ok, res):
        self.btn_csv.state(["!disabled"])
        if not ok:
            self.csv_msg.config(text="")
            messagebox.showerror("Import failed", str(res))
            return
        if not res.records:
            reasons = "; ".join(f"{n} x {w}" for w, n in res.skipped.items()) or "no rows"
            self.csv_msg.config(text="")
            messagebox.showwarning("Nothing to import", f"No usable rows were found ({reasons}).\n\n"
                                   "Check the column choices, the date order and the temperature unit.")
            return
        known = {n.lower(): n for n in self.cities}
        names = sorted({c for c, _ in res.records})
        new = [n for n in names if n.lower() not in known]
        msg = f"Import {len(res.records)} daily readings for {len(names)} city(ies)?"
        if new:
            msg += (f"\n\n{len(new)} new city(ies) will be created: {', '.join(new[:8])}{'...' if len(new) > 8 else ''}"
                    "\n(their 'normal max' is set to the average of the imported max temperatures - "
                    "adjust it later in the Cities tab)")
        if not messagebox.askyesno("Confirm import", msg):
            self.csv_msg.config(text="Import cancelled.")
            return
        ids = {}
        for n in names:
            if n.lower() in known:
                ids[n] = self.cities[known[n.lower()]]
            else:
                vals = [v["max"] for (c, _), v in res.records.items() if c == n]
                ids[n] = add_city(n, "", round(sum(vals) / len(vals), 1))
        n_rows = bulk_add_readings((ids[c], d, v["max"], v["min"], v["hum"]) for (c, d), v in res.records.items())
        self.reload_cities()
        self.refresh_all()
        notes = [f"Imported {n_rows} readings ({len(new)} new cities)."]
        if res.skipped:
            notes.append("Skipped rows: " + ", ".join(f"{n} {w}" for w, n in res.skipped.items()) + ".")
        if res.estimated_min:
            notes.append(f"{res.estimated_min} days had no min temp (estimated as max - 12 \u00b0C).")
        if res.defaulted_hum:
            notes.append(f"{res.defaulted_hum} days had no humidity (used {self.v_defhum.get()} %).")
        self.csv_msg.config(text="  ".join(notes))

    def _download(self):
        name = self.v_net_city.get()
        try:
            days = int(float(self.v_net_days.get()))
            if not 3 <= days <= 3650:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid input", "'Past days' must be a whole number between 3 and 3650.")
            return
        hum = self._default_humidity()
        if hum is None:
            return
        row = self.city_rows[name]
        self.btn_net.state(["disabled"])
        self.net_msg.config(text=f"Downloading {days} days for {name}...")

        def work():
            lat, lon, found = row["latitude"], row["longitude"], False
            if lat is None or lon is None:
                hits = geocode(name)
                if not hits:
                    raise LookupError(f"Could not find coordinates for '{name}'. Enter them in the Cities tab.")
                _, lat, lon = hits[0]
                found = True
            rows, info = fetch_open_meteo(lat, lon, days, hum)
            return lat, lon, found, rows, info

        def done(ok, val):
            self.btn_net.state(["!disabled"])
            if not ok:
                self.net_msg.config(text="")
                messagebox.showerror("Download failed", self._net_error(val))
                return
            lat, lon, found, rows, info = val
            if not rows:
                self.net_msg.config(text="The server returned no data for that period.")
                return
            if found:
                set_city_coords(row["id"], lat, lon)
            n = bulk_add_readings((row["id"], d, mx, mn, h) for d, mx, mn, h in rows)
            self.reload_cities()
            self.refresh_all()
            extra = f" ({info['no_humidity']} days had no humidity, used default)" if info["no_humidity"] else ""
            self.net_msg.config(text=f"Imported {n} days for {name}: {info['start']} to {info['end']}{extra}.")
        self._run_bg(work, done)

    # ---------- cities (add / edit / delete) ----------
    def _build_cities(self):
        cols = ("Name", "State", "Normal max \u00b0C", "Latitude", "Longitude", "Readings")
        wrap, self.city_tree = self._table(self.tab_city, cols, widths=[120] * 6, height=8)
        wrap.pack(fill="both", expand=True, padx=15, pady=(12, 6))
        self.city_tree.bind("<<TreeviewSelect>>", lambda e: self._city_selected())

        f = ttk.LabelFrame(self.tab_city, text="  City details  ")
        f.pack(fill="x", padx=15, pady=(4, 12))
        self.cv = {k: tk.StringVar() for k in ("name", "state", "normal", "lat", "lon")}
        labels = [("name", "Name"), ("state", "State"), ("normal", "Normal max \u00b0C"), ("lat", "Latitude"), ("lon", "Longitude")]
        for i, (k, lab) in enumerate(labels):
            ttk.Label(f, text=lab).grid(row=0, column=i, sticky="w", padx=(12, 8), pady=(8, 0))
            ttk.Entry(f, textvariable=self.cv[k], width=17).grid(row=1, column=i, sticky="w", padx=(12, 8), pady=(0, 8))
        bt = ttk.Frame(f)
        bt.grid(row=2, column=0, columnspan=5, sticky="w", padx=12, pady=(0, 10))
        ttk.Button(bt, text="Add as new city", style="Accent.TButton", command=self._add_city).pack(side="left")
        ttk.Button(bt, text="Save changes to selected", command=self._update_city).pack(side="left", padx=6)
        ttk.Button(bt, text="Find coordinates (online)", command=self._find_coords).pack(side="left", padx=6)
        ttk.Button(bt, text="Clear form", command=self._clear_city_form).pack(side="left", padx=6)
        ttk.Button(bt, text="Delete selected city", command=self._delete_city).pack(side="left", padx=6)
        ttk.Label(f, style="Muted.TLabel", wraplength=900, justify="left",
                  text="'Normal max' is the usual maximum temperature for the season; heatwave status is judged by how "
                       "far a reading is above it. Deleting a city also deletes its readings and alerts.").grid(
            row=3, column=0, columnspan=5, sticky="w", padx=12, pady=(0, 8))

    def _refresh_cities(self):
        counts = city_reading_counts()
        self.city_tree.delete(*self.city_tree.get_children())
        for name, c in self.city_rows.items():
            self.city_tree.insert("", "end", iid=str(c["id"]), values=(
                name, c["state"] or "", c["normal_max"],
                "" if c["latitude"] is None else c["latitude"],
                "" if c["longitude"] is None else c["longitude"], counts.get(c["id"], 0)))

    def _city_selected(self):
        sel = self.city_tree.selection()
        c = get_city(int(sel[0])) if sel else None
        if c:
            self.cv["name"].set(c["name"])
            self.cv["state"].set(c["state"] or "")
            self.cv["normal"].set(c["normal_max"])
            self.cv["lat"].set("" if c["latitude"] is None else c["latitude"])
            self.cv["lon"].set("" if c["longitude"] is None else c["longitude"])

    def _clear_city_form(self):
        for v in self.cv.values():
            v.set("")
        self.city_tree.selection_remove(self.city_tree.selection())

    def _read_city_form(self):
        name = self.cv["name"].get().strip()
        if not name:
            raise ValueError("City name is required.")
        try:
            normal = float(self.cv["normal"].get())
        except ValueError:
            raise ValueError("Normal max temperature must be a number, e.g. 38.5")
        if not 15 <= normal <= 55:
            raise ValueError("Normal max temperature should be between 15 and 55 \u00b0C.")
        lat_s, lon_s = self.cv["lat"].get().strip(), self.cv["lon"].get().strip()
        lat = lon = None
        if lat_s or lon_s:
            try:
                lat, lon = float(lat_s), float(lon_s)
            except ValueError:
                raise ValueError("Latitude and longitude must both be numbers (or both empty).")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Latitude must be -90..90 and longitude -180..180.")
        return name, self.cv["state"].get().strip(), normal, lat, lon

    def _add_city(self):
        try:
            add_city(*self._read_city_form())
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "A city with this name already exists.")
            return
        self.reload_cities()
        self.refresh_all()
        self._clear_city_form()

    def _update_city(self):
        sel = self.city_tree.selection()
        if not sel:
            messagebox.showinfo("Update", "Select a city in the table first.")
            return
        try:
            update_city(int(sel[0]), *self._read_city_form())
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate", "Another city already has this name.")
            return
        self.reload_cities()
        self.refresh_all()

    def _delete_city(self):
        sel = self.city_tree.selection()
        if not sel:
            messagebox.showinfo("Delete", "Select a city in the table first.")
            return
        if len(self.cities) <= 1:
            messagebox.showwarning("Delete", "At least one city must remain.")
            return
        cid = int(sel[0])
        n = city_reading_counts().get(cid, 0)
        if messagebox.askyesno("Delete city", f"Delete this city and its {n} reading(s) and alerts? This cannot be undone."):
            delete_city(cid)
            self._clear_city_form()
            self.reload_cities()
            self.refresh_all()

    def _find_coords(self):
        name = self.cv["name"].get().strip()
        if not name:
            messagebox.showinfo("Find coordinates", "Type the city name first.")
            return

        def done(ok, hits):
            if not ok:
                messagebox.showerror("Lookup failed", self._net_error(hits))
            elif not hits:
                messagebox.showinfo("Find coordinates", f"No place found for '{name}'.")
            else:
                label, lat, lon = hits[0]
                self.cv["lat"].set(round(lat, 4))
                self.cv["lon"].set(round(lon, 4))
                parts = [p.strip() for p in label.split(",")]
                if not self.cv["state"].get().strip() and len(parts) > 1:
                    self.cv["state"].set(parts[1])
        self._run_bg(lambda: geocode(name), done)

    # ---------- forecast ----------
    def _build_forecast(self):
        top = ttk.Frame(self.tab_fc)
        top.pack(fill="x", padx=15, pady=12)
        ttk.Label(top, text="City:").pack(side="left")
        self.v_fc_city = tk.StringVar(value=next(iter(self.cities)))
        cb = ttk.Combobox(top, textvariable=self.v_fc_city, values=list(self.cities), state="readonly", width=18)
        cb.pack(side="left", padx=8)
        self._register_box(cb, self.v_fc_city)
        cb.bind("<<ComboboxSelected>>", lambda e: self._run_forecast())
        ttk.Button(top, text="Run forecast", style="Accent.TButton", command=self._run_forecast).pack(side="left", padx=6)
        ttk.Button(top, text="Issue early warning (save alert)", style="Accent.TButton",
                   command=self._issue_alert).pack(side="left", padx=6)
        self.fc_canvas = tk.Canvas(self.tab_fc, bg=CARD, height=300, highlightthickness=0)
        self.fc_canvas.pack(fill="both", expand=True, padx=15)
        self.fc_canvas.bind("<Configure>", lambda e: self._run_forecast())
        cols = ("Date", "Forecast Max \u00b0C", "Heat Index \u00b0C", "Status")
        wrap, self.fc_tree = self._table(self.tab_fc, cols, height=3)
        wrap.pack(fill="x", padx=15, pady=8)
        self.fc_msg = tk.Label(self.tab_fc, text="", bg=BG, fg=INK, wraplength=900, justify="left", font=("Segoe UI", 10))
        self.fc_msg.pack(anchor="w", padx=15, pady=(0, 10))

    def _run_forecast(self):
        city = self.v_fc_city.get()
        self.fc = None
        self.fc_tree.delete(*self.fc_tree.get_children())
        hist = get_history(self.cities[city])
        if len(hist) < 3:
            self.fc_canvas.delete("all")
            self.fc_msg.config(text=f"{city}: need at least 3 readings to forecast.")
            return
        normal = self.city_rows[city]["normal_max"]
        self.fc, slope = make_forecast(hist, normal)
        for f in self.fc:
            self.fc_tree.insert("", "end", tags=(f["level"],), values=(f["day"], f["max_temp"], f["heat_index"], f["level"]))
        trend = "rising" if slope > 0.05 else "falling" if slope < -0.05 else "steady"
        self.fc_msg.config(text=f"Trend: {trend} ({slope:+.2f} \u00b0C/day).  " + early_warning(city, self.fc)[1])
        self._draw_forecast(hist, normal)

    def _draw_forecast(self, hist, normal):
        cv = self.fc_canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        temps = [r["max_temp"] for r in hist] + [f["max_temp"] for f in self.fc]
        lo, hi = min(temps + [normal]) - 2, max(temps + [normal]) + 2
        left, right, top, bottom = 45, w - 20, 20, h - 30
        n = len(temps)
        px = lambda i: left + i * (right - left) / (n - 1)
        py = lambda t: bottom - (t - lo) / (hi - lo) * (bottom - top)
        for t in range(int(lo), int(hi) + 1, 2):
            cv.create_line(left, py(t), right, py(t), fill="#26405f")
            cv.create_text(left - 6, py(t), text=str(t), fill=MUTED, anchor="e", font=("Segoe UI", 8))
        cv.create_line(left, py(normal), right, py(normal), fill="#ff4d4d", dash=(5, 3))
        cv.create_text(right, py(normal) - 8, text=f"normal {normal}", fill="#ff4d4d", anchor="e", font=("Segoe UI", 8))
        k = len(hist)
        pts = [(px(i), py(t)) for i, t in enumerate(temps[:k])]
        for a, b in zip(pts, pts[1:]):
            cv.create_line(*a, *b, fill="#5fb3ff", width=3)
        fpts = [pts[-1]] + [(px(i), py(t)) for i, t in enumerate(temps) if i >= k]
        for a, b in zip(fpts, fpts[1:]):
            cv.create_line(*a, *b, fill=ACCENT, width=3, dash=(6, 4))
        for i, (x, y) in enumerate(pts + fpts[1:]):
            col = "#5fb3ff" if i < k else COLORS[self.fc[i - k]["level"]]
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")
        cv.create_text(left, h - 12, text=hist[0]["day"], fill=MUTED, anchor="w", font=("Segoe UI", 8))
        cv.create_text(right, h - 12, text=self.fc[-1]["day"] + "  (forecast)", fill=ACCENT, anchor="e", font=("Segoe UI", 8))

    def _issue_alert(self):
        city = self.v_fc_city.get()
        self._run_forecast()
        if not self.fc:
            messagebox.showinfo("Early warning", "Need at least 3 readings for this city to forecast.")
            return
        level, msg = early_warning(city, self.fc)
        save_alert(self.cities[city], date.today().isoformat(), level, msg)
        self._refresh_alerts()
        messagebox.showinfo("Early warning saved", f"{level}\n\n{msg}")

    # ---------- alerts ----------
    def _build_alerts(self):
        cols = ("ID", "City", "Date", "Level", "Message")
        wrap, self.al_tree = self._table(self.tab_alerts, cols, widths=[50, 100, 100, 130, 600])
        self.al_tree.column("Message", anchor="w")
        wrap.pack(fill="both", expand=True, padx=15, pady=(15, 5))
        ttk.Button(self.tab_alerts, text="Delete selected alert", style="Accent.TButton",
                   command=self._delete_alert).pack(anchor="e", padx=15, pady=10)

    def _refresh_alerts(self):
        self.al_tree.delete(*self.al_tree.get_children())
        for a in get_alerts():
            self.al_tree.insert("", "end", tags=(a["level"],), values=(a["id"], a["city"], a["day"], a["level"], a["message"]))

    def _delete_alert(self):
        sel = self.al_tree.selection()
        if sel and messagebox.askyesno("Delete", "Delete the selected alert?"):
            delete_alert(self.al_tree.item(sel[0])["values"][0])
            self._refresh_alerts()

    def refresh_all(self):
        self._refresh_dashboard()
        self._refresh_data()
        self._refresh_cities()
        self._refresh_alerts()
        self._run_forecast()


if __name__ == "__main__":
    HeatwaveApp().mainloop()
