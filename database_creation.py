import sqlite3
import pandas as pd

conn = sqlite3.connect("speed_monitor.db")

# Load CSVs
vehicles = pd.read_csv("vehicles.csv")
zones = pd.read_csv("zones.csv")
events = pd.read_csv("events.csv")
notifications = pd.read_csv("notifications.csv")

# Write to DB
vehicles.to_sql("vehicles", conn, if_exists="replace", index=False)
zones.to_sql("zones", conn, if_exists="replace", index=False)
events.to_sql("events", conn, if_exists="replace", index=False)
notifications.to_sql("notifications", conn, if_exists="replace", index=False)

print("✅ SQLite DB ready")