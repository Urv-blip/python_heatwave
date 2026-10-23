"""database.py - SQLite layer for Heatwave Guard (Climate Intelligence project)."""
import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).with_name("heatwave.db")

# (city, state, latitude, longitude, fallback normal max in deg C)
# The fallback is replaced by a real 10-year average once live data is fetched.
CITIES = [
    ("Delhi", "Delhi", 28.61, 77.21, 39.0), ("Nagpur", "Maharashtra", 21.15, 79.09, 38.0),
    ("Jaipur", "Rajasthan", 26.91, 75.79, 39.0), ("Ahmedabad", "Gujarat", 23.02, 72.57, 39.5),
    ("Mumbai", "Maharashtra", 19.08, 72.88, 33.0), ("Hyderabad", "Telangana", 17.39, 78.49, 37.0),
    ("Chennai", "Tamil Nadu", 13.08, 80.27, 36.0), ("Bengaluru", "Karnataka", 12.97, 77.59, 34.0),
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed=False):
    """Create tables and the city list. seed=True adds SIMULATED readings (offline demo only)."""
    with connect() as c:
        cols = [r["name"] for r in c.execute("PRAGMA table_info(cities)")]
        if cols and "lat" not in cols:      # old version of the database -> rebuild
            c.executescript("DROP TABLE IF EXISTS alerts; DROP TABLE IF EXISTS readings; DROP TABLE IF EXISTS cities;")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, state TEXT, lat REAL, lon REAL,
            normal_max REAL NOT NULL, normal_src TEXT DEFAULT 'default');
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
        c.executemany("INSERT OR IGNORE INTO cities(name,state,lat,lon,normal_max) VALUES(?,?,?,?,?)", CITIES)
        if seed and c.execute("SELECT COUNT(*) FROM readings").fetchone()[0] == 0:
            _seed(c)


def _seed(c, days=14):
    """SIMULATED readings (offline demo only): warming trend + noise."""
    rnd = random.Random(42)
    today = date.today()
    for city in c.execute("SELECT id, name, normal_max FROM cities").fetchall():
        inland = city["name"] in ("Delhi", "Nagpur", "Jaipur", "Ahmedabad")
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            warm = (0.45 if inland else 0.12) * i + rnd.uniform(-1.2, 1.2)
            tmax = round(city["normal_max"] - 1.5 + warm, 1)
            hum = round(rnd.uniform(25, 45) if inland else rnd.uniform(55, 80), 0)
            c.execute("INSERT INTO readings(city_id,day,max_temp,min_temp,humidity) VALUES(?,?,?,?,?)",
                      (city["id"], d.isoformat(), tmax, round(tmax - rnd.uniform(9, 14), 1), hum))


def get_cities():
    with connect() as c:
        return c.execute("SELECT * FROM cities ORDER BY name").fetchall()


def set_normal(city_id, value, source):
    with connect() as c:
        c.execute("UPDATE cities SET normal_max=?, normal_src=? WHERE id=?", (value, source, city_id))


def add_reading(city_id, day, max_temp, min_temp, humidity):
    add_readings(city_id, [(day, max_temp, min_temp, humidity)])


def add_readings(city_id, rows):
    """Insert or update many (day, max, min, humidity) rows for one city."""
    with connect() as c:
        c.executemany("""INSERT INTO readings(city_id,day,max_temp,min_temp,humidity)
                     VALUES(?,?,?,?,?)
                     ON CONFLICT(city_id,day) DO UPDATE SET max_temp=excluded.max_temp,
                     min_temp=excluded.min_temp, humidity=excluded.humidity""",
                      [(city_id, *r) for r in rows])


def get_history(city_id, limit=14):
    """Last `limit` readings of a city, oldest first."""
    with connect() as c:
        rows = c.execute("SELECT * FROM readings WHERE city_id=? ORDER BY day DESC LIMIT ?",
                         (city_id, limit)).fetchall()
    return list(reversed(rows))


def latest_per_city():
    with connect() as c:
        return c.execute("""SELECT c.id city_id, c.name, c.state, c.normal_max,
               r.day, r.max_temp, r.min_temp, r.humidity FROM cities c
               JOIN readings r ON r.city_id=c.id
               WHERE r.day=(SELECT MAX(day) FROM readings WHERE city_id=c.id)
               ORDER BY c.name""").fetchall()


def save_alert(city_id, day, level, message):
    with connect() as c:
        c.execute("INSERT INTO alerts(city_id,day,level,message) VALUES(?,?,?,?)",
                  (city_id, day, level, message))


def get_alerts(limit=100):
    with connect() as c:
        return c.execute("""SELECT a.id, c.name city, a.day, a.level, a.message, a.created_at
               FROM alerts a JOIN cities c ON c.id=a.city_id
               ORDER BY a.id DESC LIMIT ?""", (limit,)).fetchall()


def delete_alert(alert_id):
    with connect() as c:
        c.execute("DELETE FROM alerts WHERE id=?", (alert_id,))


def add_city(name, state, normal_max):
    """Add a new city. Returns its id, or None if the name already exists."""
    try:
        with connect() as c:
            return c.execute("INSERT INTO cities(name,state,normal_max) VALUES(?,?,?)",
                             (name, state, normal_max)).lastrowid
    except sqlite3.IntegrityError:
        return None


def import_csv(path):
    """Bulk import. CSV columns: city,state,normal_max,day,max_temp,min_temp,humidity
    Unknown cities are created. Returns (rows_imported, list_of_error_messages)."""
    import csv
    from datetime import date as _d
    ok, errors = 0, []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for n, row in enumerate(csv.DictReader(fh), start=2):
            try:
                name = row["city"].strip()
                tmax, tmin, hum = float(row["max_temp"]), float(row["min_temp"]), float(row["humidity"])
                day = _d.fromisoformat(row["day"].strip()).isoformat()
                if not name or not (-10 <= tmin <= tmax <= 60) or not (0 <= hum <= 100):
                    raise ValueError("value out of range")
                with connect() as c:
                    r = c.execute("SELECT id FROM cities WHERE name=?", (name,)).fetchone()
                if r:
                    cid = r["id"]
                else:
                    cid = add_city(name, (row.get("state") or "").strip(), float(row["normal_max"]))
                add_reading(cid, day, tmax, tmin, hum)
                ok += 1
            except (KeyError, ValueError, TypeError) as e:
                errors.append(f"line {n}: {e}")
    return ok, errors
