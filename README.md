# Heatwave Guard
Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning (Python Mini Project)

Files: database.py (SQLite) | predictor.py (heat index, risk, forecast)
       app.py (Tkinter GUI) | web_export.py (HTML/CSS website) |
       heatwave_guard.py (combined tkinter file)

Run (Python 3.8+, standard library only):
  python app.py                 # desktop app; fetches live data on start, button to refresh
  python web_export.py          # website with SIMULATED demo data -> website/index.html (open in browser)
 
Notes: "normal" temperature = 10-year ERA5 average for +/-7 days around today's date.
Today's daily maximum is the model value for the full day. If you delete heatwave.db it is rebuilt.

Website 'Add Reading' tab: readings you add are stored in the browser (localStorage), not in heatwave.db.
The Tkinter app writes to SQLite. Use 'Reset to demo data' on the site to clear browser entries.
