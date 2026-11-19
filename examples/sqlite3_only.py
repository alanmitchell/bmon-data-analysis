"""Querying the two SQLite databases with Python's built-in sqlite3 module,
for when you would rather not use DuckDB.

Run with:   uv run examples/sqlite3_only.py

The important part is opening the file READ-ONLY. A plain
sqlite3.connect('bmon.sqlite') opens the database read/write, and will even
create an empty database if the path is wrong. bmon_data.sqlite_django() and
bmon_data.sqlite_readings() do it the safe way, which is:

    conn = sqlite3.connect("file:/path/to/bmon.sqlite?mode=ro", uri=True)
"""
import sqlite3
from datetime import datetime

import pandas as pd

import bmon_data
from bmon_data import settings

# --- The Django database. Rows can be read by column name.
django = bmon_data.sqlite_django()
print("Buildings:")
for row in django.execute("SELECT id, title FROM bmsapp_building ORDER BY title LIMIT 5"):
    print(f"  {row['id']:4d}  {row['title']}")

# --- The reading database. Every table is one sensor's readings (apart from
# a few tables whose names start with '_').
readings = bmon_data.sqlite_readings()
tables = {row["name"] for row in readings.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

# Pick a temperature sensor that has a table; a sensor that has never
# reported does not.
sensor_id = next(
    row["sensor_id"]
    for row in django.execute(
        "SELECT sensor_id FROM bmsapp_sensor WHERE title LIKE '%temperature%' ORDER BY sensor_id"
    )
    if row["sensor_id"] in tables
)

# The table name is the sensor ID, in "double quotes" or [brackets].
# Timestamps are Unix seconds.
print(f"\nLast readings of {sensor_id}:")
for row in readings.execute(f'SELECT ts, val FROM "{sensor_id}" ORDER BY ts DESC LIMIT 5'):
    print(f"  {datetime.fromtimestamp(row['ts']):%Y-%m-%d %H:%M:%S}  {row['val']}")

# Pandas can read from the connection directly.
df = pd.read_sql(f'SELECT ts, val FROM "{sensor_id}" ORDER BY ts DESC LIMIT 1000', readings)
df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert("America/Anchorage")
print(f"\nAs a DataFrame:\n{df.head()}")

# --- The same thing written out without the bmon_data helper.
conn = sqlite3.connect(f"{settings.DJANGO_DB.as_uri()}?mode=ro", uri=True)
print("\nNumber of sensors:", conn.execute("SELECT count(*) FROM bmsapp_sensor").fetchone()[0])

# A write is refused:
try:
    conn.execute("DELETE FROM bmsapp_sensor")
except sqlite3.OperationalError as e:
    print("Write refused, as it should be:", e)
