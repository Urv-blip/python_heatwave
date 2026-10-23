# Heatwave Guard
Climate Intelligence for Heatwave Monitoring, Prediction and Early Warning (Python Mini Project)

Files: database.py (SQLite) | predictor.py (heat index, risk, forecast)
       app.py (Tkinter GUI) | web_export.py (HTML/CSS website) |
       heatwave_guard.py (combined tkinter file)

Notes: "normal" temperature = 10-year ERA5 average for +/-7 days around today's date.
Today's daily maximum is the model value for the full day. If you delete heatwave.db it is rebuilt.

