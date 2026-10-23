"""app.py - Heatwave Guard: Tkinter desktop front end (SQLite backend).
Run:  python app.py
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import date

import database as db
import live_data
import predictor as pr

BG, CARD, INK, ACCENT = "#0f1b2d", "#17283f", "#eef3fa", "#ff8a3d"


class HeatwaveApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Heatwave Guard - Climate Intelligence for Heatwave Monitoring")
        self.geometry("1020x680")
        self.minsize(900, 600)
        self.configure(bg=BG)
        db.init_db()
        self.cities = {c["name"]: c["id"] for c in db.get_cities()}
        self._style()
        self._header()
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tab_dash, self.tab_add = ttk.Frame(nb), ttk.Frame(nb)
        self.tab_fc, self.tab_alerts = ttk.Frame(nb), ttk.Frame(nb)
        for tab, label in ((self.tab_dash, "  Dashboard  "), (self.tab_add, "  Add Reading  "),
                           (self.tab_fc, "  Forecast & Early Warning  "), (self.tab_alerts, "  Alert Log  ")):
            nb.add(tab, text=label)
        self._build_dashboard()
        self._build_add()
        self._build_forecast()
        self._build_alerts()
        self.refresh_all()
        self.live_refresh()          # fetch real data in the background

    # ---------- look & feel ----------
    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=INK, font=("Segoe UI", 10))
        s.configure("H.TLabel", font=("Segoe UI", 13, "bold"))
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=CARD, foreground=INK, padding=(6, 8), font=("Segoe UI", 10, "bold"))
        s.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#101010")])
        s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=INK, rowheight=28, font=("Segoe UI", 10))
        s.configure("Treeview.Heading", background="#22385a", foreground=INK, font=("Segoe UI", 10, "bold"))
        s.configure("Accent.TButton", background=ACCENT, foreground="#101010", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Accent.TButton", background=[("active", "#ffa05f")])

    def _header(self):
        f = tk.Frame(self, bg=BG)
        f.pack(fill="x", padx=16, pady=12)
        tk.Label(f, text="\u2600  Heatwave Guard", bg=BG, fg=ACCENT, font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(f, text="Monitoring  \u2022  Prediction  \u2022  Early Warning", bg=BG, fg="#9fb3cf",
                 font=("Segoe UI", 11)).pack(side="left", padx=18, pady=(8, 0))
        tk.Button(f, text="\u21bb Refresh live data", command=self.live_refresh, bg=ACCENT, fg="#101010",
                  relief="flat", font=("Segoe UI", 10, "bold"), padx=10, pady=4).pack(side="right")
        self.status = tk.Label(f, text="", bg=BG, fg="#9fb3cf", font=("Segoe UI", 9))
        self.status.pack(side="right", padx=12)

    # ---------- dashboard ----------
    def _build_dashboard(self):
        top = ttk.Frame(self.tab_dash)
        top.pack(fill="x", padx=10, pady=10)
        self.cards = {}
        for lvl in pr.LEVELS:
            c = tk.Frame(top, bg=CARD, highlightthickness=2, highlightbackground=pr.COLORS[lvl])
            c.pack(side="left", expand=True, fill="x", padx=5)
            n = tk.Label(c, text="0", bg=CARD, fg=pr.COLORS[lvl], font=("Segoe UI", 26, "bold"))
            n.pack(pady=(6, 0))
            tk.Label(c, text=lvl, bg=CARD, fg=INK, font=("Segoe UI", 10)).pack(pady=(0, 6))
            self.cards[lvl] = n
        cols = ("City", "State", "Date", "Max \u00b0C", "Normal \u00b0C", "Humidity %", "Heat Index \u00b0C", "Status")
        self.tree = ttk.Treeview(self.tab_dash, columns=cols, show="headings", height=8)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110, anchor="center")
        self.tree.pack(fill="x", padx=15)
        for lvl, col in pr.COLORS.items():
            self.tree.tag_configure(lvl, foreground=col)
        ttk.Label(self.tab_dash, text="Latest maximum temperature by city (red line = city normal)",
                  style="H.TLabel").pack(anchor="w", padx=15, pady=(12, 2))
        self.bar_canvas = tk.Canvas(self.tab_dash, bg=CARD, height=210, highlightthickness=0)
        self.bar_canvas.pack(fill="both", expand=True, padx=15, pady=(0, 10))
        self.bar_canvas.bind("<Configure>", lambda e: self._draw_bars())

    def _refresh_dashboard(self):
        self.tree.delete(*self.tree.get_children())
        self.latest = db.latest_per_city()
        counts = dict.fromkeys(pr.LEVELS, 0)
        for r in self.latest:
            lvl = pr.classify(r["max_temp"], r["normal_max"], r["humidity"])
            counts[lvl] += 1
            self.tree.insert("", "end", tags=(lvl,), values=(
                r["name"], r["state"], r["day"], r["max_temp"], r["normal_max"], int(r["humidity"]),
                pr.heat_index(r["max_temp"], r["humidity"]), lvl))
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
            cv.create_text(left - 6, y, text=str(t), fill="#9fb3cf", anchor="e", font=("Segoe UI", 8))
        for i, r in enumerate(rows):
            lvl = pr.classify(r["max_temp"], r["normal_max"], r["humidity"])
            x0 = left + i * slot + slot * 0.2
            x1 = left + (i + 1) * slot - slot * 0.2
            y = bottom - r["max_temp"] * scale
            cv.create_rectangle(x0, y, x1, bottom, fill=pr.COLORS[lvl], outline="")
            cv.create_text((x0 + x1) / 2, y - 8, text=f'{r["max_temp"]}', fill=INK, font=("Segoe UI", 9, "bold"))
            cv.create_text((x0 + x1) / 2, bottom + 12, text=r["name"], fill=INK, font=("Segoe UI", 9))
            yn = bottom - r["normal_max"] * scale
            cv.create_line(x0 - 6, yn, x1 + 6, yn, fill="#ff4d4d", width=2)

    # ---------- add reading ----------
    def _build_add(self):
        f = ttk.Frame(self.tab_add)
        f.pack(side="left", padx=30, pady=25, anchor="n")
        ttk.Label(f, text="Record a daily weather observation", style="H.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))
        self.v_city = tk.StringVar(value=next(iter(self.cities)))
        self.v_day = tk.StringVar(value=date.today().isoformat())
        self.v_max, self.v_min, self.v_hum = tk.StringVar(), tk.StringVar(), tk.StringVar()
        fields = [("City", ttk.Combobox(f, textvariable=self.v_city, values=list(self.cities), state="readonly", width=28)),
                  ("Date (YYYY-MM-DD)", ttk.Entry(f, textvariable=self.v_day, width=30)),
                  ("Max temperature (\u00b0C)", ttk.Entry(f, textvariable=self.v_max, width=30)),
                  ("Min temperature (\u00b0C)", ttk.Entry(f, textvariable=self.v_min, width=30)),
                  ("Relative humidity (%)", ttk.Entry(f, textvariable=self.v_hum, width=30))]
        for i, (lab, w) in enumerate(fields, start=1):
            ttk.Label(f, text=lab).grid(row=i, column=0, sticky="w", pady=7, padx=(0, 20))
            w.grid(row=i, column=1, sticky="w")
        ttk.Button(f, text="Save Reading", style="Accent.TButton", command=self._save_reading).grid(row=7, column=1, sticky="w", pady=18)
        self.add_msg = ttk.Label(f, text="")
        self.add_msg.grid(row=8, column=0, columnspan=2, sticky="w")
        self.cb_add = fields[0][1]
        self._build_city_form()

    def _save_reading(self):
        try:
            day = date.fromisoformat(self.v_day.get().strip()).isoformat()
            tmax, tmin, hum = float(self.v_max.get()), float(self.v_min.get()), float(self.v_hum.get())
            if not (-10 <= tmin <= tmax <= 60):
                raise ValueError("Temperatures must satisfy -10 <= min <= max <= 60 \u00b0C.")
            if not (0 <= hum <= 100):
                raise ValueError("Humidity must be between 0 and 100 %.")
        except ValueError as e:
            messagebox.showerror("Invalid input", f"Please check the values.\n\n{e}")
            return
        db.add_reading(self.cities[self.v_city.get()], day, tmax, tmin, hum)
        lvl = pr.classify(tmax, next(c["normal_max"] for c in db.get_cities() if c["name"] == self.v_city.get()), hum)
        self.add_msg.config(text=f"Saved. Status for {self.v_city.get()} on {day}: {lvl}")
        self.refresh_all()

    # ---------- add city / import ----------
    def _build_city_form(self):
        g = ttk.Frame(self.tab_add)
        g.pack(side="left", padx=40, pady=25, anchor="n")
        ttk.Label(g, text="Add a new city", style="H.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 15))
        self.v_cname, self.v_cstate, self.v_cnorm = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for i, (lab, var) in enumerate((("City name", self.v_cname), ("State", self.v_cstate),
                                        ("Normal max temp (\u00b0C)", self.v_cnorm)), start=1):
            ttk.Label(g, text=lab).grid(row=i, column=0, sticky="w", pady=7, padx=(0, 20))
            ttk.Entry(g, textvariable=var, width=26).grid(row=i, column=1, sticky="w")
        ttk.Button(g, text="Add City", style="Accent.TButton", command=self._save_city).grid(row=4, column=1, sticky="w", pady=14)
        ttk.Label(g, text="Bulk import from CSV", style="H.TLabel").grid(row=5, column=0, columnspan=2, sticky="w", pady=(20, 4))
        ttk.Label(g, text="Columns: city,state,normal_max,day,max_temp,min_temp,humidity\n(see sample_data.csv)").grid(row=6, column=0, columnspan=2, sticky="w")
        ttk.Button(g, text="Import CSV...", style="Accent.TButton", command=self._import_csv).grid(row=7, column=1, sticky="w", pady=14)
        self.city_msg = ttk.Label(g, text="", wraplength=330)
        self.city_msg.grid(row=8, column=0, columnspan=2, sticky="w")

    def _sync_cities(self):
        """Reload city list and refresh every dropdown."""
        self.cities = {c["name"]: c["id"] for c in db.get_cities()}
        names = list(self.cities)
        self.cb_add["values"] = names
        self.cb_fc["values"] = names

    def _save_city(self):
        name, state = self.v_cname.get().strip(), self.v_cstate.get().strip()
        try:
            normal = float(self.v_cnorm.get())
            if not name:
                raise ValueError("City name is required.")
            if not (20 <= normal <= 50):
                raise ValueError("Normal max temperature should be between 20 and 50 \u00b0C.")
        except ValueError as e:
            messagebox.showerror("Invalid input", str(e))
            return
        if db.add_city(name, state, normal) is None:
            messagebox.showwarning("Duplicate", f"'{name}' already exists.")
            return
        self._sync_cities()
        self.v_city.set(name)
        self.city_msg.config(text=f"'{name}' added. Now add at least 3 daily readings for it (left form) to see it on the dashboard and forecast.")
        self.v_cname.set(""); self.v_cstate.set(""); self.v_cnorm.set("")

    def _import_csv(self):
        path = filedialog.askopenfilename(title="Select CSV file", filetypes=[("CSV files", "*.csv")])
        if not path:
            return
        try:
            ok, errors = db.import_csv(path)
        except (OSError, UnicodeDecodeError) as e:
            messagebox.showerror("Import failed", str(e))
            return
        self._sync_cities()
        self.refresh_all()
        msg = f"Imported {ok} rows."
        if errors:
            msg += f" Skipped {len(errors)}: " + "; ".join(errors[:3])
        self.city_msg.config(text=msg)

    # ---------- forecast ----------
    def _build_forecast(self):
        top = ttk.Frame(self.tab_fc)
        top.pack(fill="x", padx=15, pady=12)
        ttk.Label(top, text="City:").pack(side="left")
        self.v_fc_city = tk.StringVar(value=next(iter(self.cities)))
        cb = ttk.Combobox(top, textvariable=self.v_fc_city, values=list(self.cities), state="readonly", width=18)
        cb.pack(side="left", padx=8)
        self.cb_fc = cb
        cb.bind("<<ComboboxSelected>>", lambda e: self._run_forecast())
        ttk.Button(top, text="Run forecast", style="Accent.TButton", command=self._run_forecast).pack(side="left", padx=6)
        ttk.Button(top, text="Issue early warning (save alert)", style="Accent.TButton", command=self._issue_alert).pack(side="left", padx=6)
        self.fc_canvas = tk.Canvas(self.tab_fc, bg=CARD, height=300, highlightthickness=0)
        self.fc_canvas.pack(fill="both", expand=True, padx=15)
        self.fc_canvas.bind("<Configure>", lambda e: self._run_forecast())
        cols = ("Date", "Forecast Max \u00b0C", "Heat Index \u00b0C", "Status")
        self.fc_tree = ttk.Treeview(self.tab_fc, columns=cols, show="headings", height=3)
        for c in cols:
            self.fc_tree.heading(c, text=c)
            self.fc_tree.column(c, anchor="center")
        for lvl, col in pr.COLORS.items():
            self.fc_tree.tag_configure(lvl, foreground=col)
        self.fc_tree.pack(fill="x", padx=15, pady=8)
        self.fc_msg = tk.Label(self.tab_fc, text="", bg=BG, fg=INK, wraplength=900, justify="left", font=("Segoe UI", 10))
        self.fc_msg.pack(anchor="w", padx=15, pady=(0, 10))

    def _run_forecast(self):
        city = self.v_fc_city.get()
        hist = db.get_history(self.cities[city])
        if len(hist) < 3:
            self.fc = None
            self.fc_msg.config(text="Need at least 3 readings to forecast (connect to the internet and refresh).")
            return
        normal = next(c["normal_max"] for c in db.get_cities() if c["name"] == city)
        self.fc, slope = pr.forecast(hist, normal)
        self.fc_tree.delete(*self.fc_tree.get_children())
        for f in self.fc:
            self.fc_tree.insert("", "end", tags=(f["level"],), values=(f["day"], f["max_temp"], f["heat_index"], f["level"]))
        trend = "rising" if slope > 0.05 else "falling" if slope < -0.05 else "steady"
        self.fc_msg.config(text=f"Trend: {trend} ({slope:+.2f} \u00b0C/day).  " + pr.early_warning(city, self.fc)[1])
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
            cv.create_text(left - 6, py(t), text=str(t), fill="#9fb3cf", anchor="e", font=("Segoe UI", 8))
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
            col = "#5fb3ff" if i < k else pr.COLORS[self.fc[i - k]["level"]]
            cv.create_oval(x - 4, y - 4, x + 4, y + 4, fill=col, outline="")
        cv.create_text(left, h - 12, text=hist[0]["day"], fill="#9fb3cf", anchor="w", font=("Segoe UI", 8))
        cv.create_text(right, h - 12, text=self.fc[-1]["day"] + "  (forecast)", fill=ACCENT, anchor="e", font=("Segoe UI", 8))

    def _issue_alert(self):
        city = self.v_fc_city.get()
        self._run_forecast()
        if not getattr(self, "fc", None):
            messagebox.showwarning("No data", "No readings yet. Refresh live data first.")
            return
        level, msg = pr.early_warning(city, self.fc)
        db.save_alert(self.cities[city], date.today().isoformat(), level, msg)
        self._refresh_alerts()
        messagebox.showinfo("Early warning saved", f"{level}\n\n{msg}")

    # ---------- alerts ----------
    def _build_alerts(self):
        cols = ("ID", "City", "Date", "Level", "Message")
        self.al_tree = ttk.Treeview(self.tab_alerts, columns=cols, show="headings")
        widths = (50, 100, 100, 130, 600)
        for c, wd in zip(cols, widths):
            self.al_tree.heading(c, text=c)
            self.al_tree.column(c, width=wd, anchor="w" if c == "Message" else "center")
        for lvl, col in pr.COLORS.items():
            self.al_tree.tag_configure(lvl, foreground=col)
        self.al_tree.pack(fill="both", expand=True, padx=15, pady=(15, 5))
        ttk.Button(self.tab_alerts, text="Delete selected alert", style="Accent.TButton",
                   command=self._delete_alert).pack(anchor="e", padx=15, pady=10)

    def _refresh_alerts(self):
        self.al_tree.delete(*self.al_tree.get_children())
        for a in db.get_alerts():
            self.al_tree.insert("", "end", tags=(a["level"],), values=(a["id"], a["city"], a["day"], a["level"], a["message"]))

    def _delete_alert(self):
        sel = self.al_tree.selection()
        if sel and messagebox.askyesno("Delete", "Delete the selected alert?"):
            db.delete_alert(self.al_tree.item(sel[0])["values"][0])
            self._refresh_alerts()

    # ---------- live data (Open-Meteo) ----------
    def live_refresh(self):
        self.status.config(text="Fetching live data from Open-Meteo...")
        self._result = None

        def work():                      # runs in a background thread
            self._result = live_data.refresh(log=lambda m: None)
        threading.Thread(target=work, daemon=True).start()
        self.after(300, self._poll)

    def _poll(self):                     # runs in the Tkinter thread
        if self._result is None:
            self.after(300, self._poll)
            return
        ok, errs = self._result
        self.refresh_all()
        msg = f"Live data updated for {ok} cities (Open-Meteo)"
        if errs:
            msg = f"Offline or failed for {len(errs)} cities - showing stored data"
        self.status.config(text=msg)

    def refresh_all(self):
        self._refresh_dashboard()
        self._refresh_alerts()
        if hasattr(self, "fc_canvas"):
            self._run_forecast()


if __name__ == "__main__":
    HeatwaveApp().mainloop()
