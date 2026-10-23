"""database.py - SQLite layer for Heatwave Guard (Climate Intelligence project)."""
import sqlite3
import random
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).with_name("heatwave.db")

# (city, state, normal maximum temperature in deg C for the season)
CITIES = [
    ("Delhi", "Delhi", 39.0), ("Nagpur", "Maharashtra", 37.0),
    ("Jaipur", "Rajasthan", 39.5), ("Ahmedabad", "Gujarat", 39.5),
    ("Mumbai", "Maharashtra", 33.0), ("Hyderabad", "Telangana", 37.0),
    ("Chennai", "Tamil Nadu", 36.0), ("Bengaluru", "Karnataka", 34.0),
]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(seed=True):
    """Create tables; fill with simulated demo data on first run."""
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS cities(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL, state TEXT, normal_max REAL NOT NULL);
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
        if seed and c.execute("SELECT COUNT(*) FROM cities").fetchone()[0] == 0:
            _seed(c)


def _seed(c, days=14):
    """Simulated readings: a warming trend + noise, hotter for inland cities."""
    rnd = random.Random(42)
    today = date.today()
    for name, state, normal in CITIES:
        cid = c.execute("INSERT INTO cities(name,state,normal_max) VALUES(?,?,?)",
                        (name, state, normal)).lastrowid
        inland = name in ("Delhi", "Nagpur", "Jaipur", "Ahmedabad")
        for i in range(days):
            d = today - timedelta(days=days - 1 - i)
            warm = (0.45 if inland else 0.12) * i + rnd.uniform(-1.2, 1.2)
            tmax = round(normal - 1.5 + warm, 1)
            hum = round(rnd.uniform(25, 45) if inland else rnd.uniform(55, 80), 0)
            c.execute("INSERT INTO readings(city_id,day,max_temp,min_temp,humidity)"
                      " VALUES(?,?,?,?,?)",
                      (cid, d.isoformat(), tmax, round(tmax - rnd.uniform(9, 14), 1), hum))


def get_cities():
    with connect() as c:
        return c.execute("SELECT * FROM cities ORDER BY name").fetchall()


def add_reading(city_id, day, max_temp, min_temp, humidity):
    """Insert or update (same city + day) a reading."""
    with connect() as c:
        c.execute("""INSERT INTO readings(city_id,day,max_temp,min_temp,humidity)
                     VALUES(?,?,?,?,?)
                     ON CONFLICT(city_id,day) DO UPDATE SET max_temp=excluded.max_temp,
                     min_temp=excluded.min_temp, humidity=excluded.humidity""",
                  (city_id, day, max_temp, min_temp, humidity))


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
