"""predictor.py - heat index, risk classification and short-term forecast (pure Python)."""
from datetime import date, timedelta

LEVELS = ["Normal", "Caution", "Heatwave", "Severe Heatwave"]
COLORS = {"Normal": "#2e9e5b", "Caution": "#e6b800",
          "Heatwave": "#ec7a1c", "Severe Heatwave": "#d62828"}
ADVICE = {
    "Normal": "No action needed. Stay hydrated as usual.",
    "Caution": "Hot conditions. Avoid strenuous outdoor work at noon; drink water often.",
    "Heatwave": "Heatwave conditions. Avoid going out 12-4 PM, protect children, elderly and outdoor workers, open cooling shelters.",
    "Severe Heatwave": "SEVERE heatwave. Stay indoors, activate emergency health response, issue public alert and arrange water/ORS distribution.",
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
    # heat index only acts as a secondary check (humid heat feels hotter)
    hi = heat_index(max_temp, humidity)
    if hi >= 54 and max_temp >= 37:
        level = max(level, 2)
    elif hi >= 41:
        level = max(level, 1)
    return LEVELS[level]


def linear_fit(ys):
    """Least-squares line y = a + b*x over x = 0..n-1. Returns (a, b)."""
    n = len(ys)
    if n < 2:
        return (ys[0] if ys else 0.0), 0.0
    mx, my = (n - 1) / 2, sum(ys) / n
    sxx = sum((i - mx) ** 2 for i in range(n))
    b = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sxx
    return my - b * mx, b


def forecast(history, normal_max, days=3):
    """Forecast next `days` from a list of readings (sqlite rows / dicts).
    Uses a linear trend on the last 7 days of max temperature and the
    mean humidity of the same window."""
    window = history[-7:]
    temps = [r["max_temp"] for r in window]
    hum = sum(r["humidity"] for r in window) / len(window)
    a, b = linear_fit(temps)
    last_day = date.fromisoformat(window[-1]["day"])
    out = []
    for k in range(1, days + 1):
        t = round(a + b * (len(temps) - 1 + k), 1)
        out.append({"day": (last_day + timedelta(days=k)).isoformat(),
                    "max_temp": t, "humidity": round(hum),
                    "heat_index": heat_index(t, hum),
                    "level": classify(t, normal_max, hum)})
    return out, b


def early_warning(city, forecast_rows):
    """Worst level in the forecast -> (level, message) for the alert log."""
    worst = max(forecast_rows, key=lambda f: LEVELS.index(f["level"]))
    if LEVELS.index(worst["level"]) == 0:
        return "Normal", f"{city}: no heatwave expected in the next {len(forecast_rows)} days."
    return worst["level"], (f"{city}: {worst['level']} likely on {worst['day']} "
                            f"(max {worst['max_temp']} C, heat index {worst['heat_index']} C). "
                            + ADVICE[worst["level"]])
