"""Example queries of the sensor reading database.

Run with:   uv run examples/readings.py

The structure of the database is described in docs/reading-db.md.
"""
import pandas as pd

import bmon_data

conn = bmon_data.connect()

# Sensor IDs differ between BMON installations, so pick some from the Django
# database: here, up to three temperature sensors from the building that has
# the most of them. A sensor that has never reported has no table in the
# reading database, so only sensors that do have a table are considered.
rows = conn.sql("""
    WITH candidates AS (
        SELECT sensor_id, sensor, building
        FROM sensors
        WHERE sensor ILIKE '%temperature%'
          AND sensor_id IN (SELECT table_name FROM duckdb_tables() WHERE database_name = 'rd')
    )
    SELECT sensor_id, sensor, building
    FROM candidates
    WHERE building = (SELECT building FROM candidates GROUP BY building ORDER BY count(*) DESC LIMIT 1)
    ORDER BY sensor_id
    LIMIT 3
""").fetchall()
sensor_ids = [row[0] for row in rows]
titles = {row[0]: row[1] for row in rows}
print(f"Sensors used in these examples, from building '{rows[0][2]}':")
for sensor_id, title in titles.items():
    print(f"  {sensor_id}: {title}")
first_id = sensor_ids[0]

# --- The readings() macro: one sensor, with real timestamps.
print(f"\nMost recent readings of {first_id}:")
conn.sql(f"SELECT ts, val FROM readings('{first_id}') ORDER BY ts DESC LIMIT 5").show()

# --- Let DuckDB do the summarizing; only the small result comes into Python.
print("Daily statistics for the sensor's last 14 days of data:")
daily = conn.sql(f"""
    SELECT
        date_trunc('day', ts)::DATE AS day,
        round(avg(val), 2) AS average,
        min(val) AS minimum,
        max(val) AS maximum,
        count(*) AS reading_count
    FROM readings('{first_id}')
    WHERE ts >= (SELECT max(ts) FROM readings('{first_id}')) - INTERVAL 14 DAY
    GROUP BY day
    ORDER BY day
""").df()
print(daily)

# --- bmon_data.sensor_readings(): several sensors and a date range, as a
# DataFrame in "long" format (one row per reading).
# Here, the 7 days up to the last reading of the first sensor.
last_ts = conn.sql(f"SELECT max(ts) FROM readings('{first_id}')").df().iloc[0, 0]
start = (last_ts - pd.Timedelta(days=7)).to_pydatetime()
end = last_ts.to_pydatetime()
df = bmon_data.sensor_readings(conn, sensor_ids, start=start, end=end)
print(f"\n{len(df)} readings from {len(sensor_ids)} sensors in the 7 days from {start:%Y-%m-%d %H:%M}:")
print(df.head())

# Pivot to "wide" format, one column per sensor, averaging readings into
# hourly intervals so that sensors reporting at different times line up.
wide = (
    df.set_index("ts")
    .groupby("sensor_id")["val"]
    .resample("1h")
    .mean()
    .unstack("sensor_id")
    .rename(columns=titles)
)
print("\nHourly averages, one column per sensor:")
print(wide.tail())

# --- The alert log is also in this database.
print("\nMost recent alerts sent:")
conn.sql("SELECT ts, building, sensor_id FROM alert_log ORDER BY ts DESC LIMIT 5").show()
