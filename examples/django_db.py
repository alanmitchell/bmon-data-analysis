"""Example queries of the Django database (buildings, sensors, alerts ...).

Run with:   uv run examples/django_db.py

Table descriptions are in docs/django-db.md.
"""
import bmon_data

# One connection gives read-only access to all three BMON data stores.
conn = bmon_data.connect()

# .show() prints a result; good for a quick look.
print("Buildings:")
conn.sql("""
    SELECT id, title, latitude, longitude, timezone
    FROM bmon.bmsapp_building
    ORDER BY title
    LIMIT 10
""").show()

# .df() returns the result as a Pandas DataFrame for further work in Python.
# The 'sensors' view joins sensors to their buildings, groups and units.
df = conn.sql("SELECT * FROM sensors").df()
print(f"{len(df)} building/sensor combinations. Sensors per building:")
print(df.groupby("building")["sensor_id"].count().sort_values(ascending=False).head(10))

# Pass values into a query with '?' placeholders rather than building the SQL
# text yourself; it avoids trouble with quotes in names.
search = "%temperature%"
print(f"\nSensors with a title like {search}:")
found = conn.sql(
    "SELECT building, sensor, sensor_id, unit FROM sensors WHERE sensor ILIKE ? LIMIT 10",
    params=[search],
).fetchall()
for building, sensor, sensor_id, unit in found:
    print(f"  {building}: {sensor}  [{sensor_id}]  ({unit})")

# Some columns hold YAML text, which needs parsing to be useful (PyYAML is not
# installed in this project; add it with 'uv add pyyaml' if you need it).
print("\nSensors with function parameters:")
conn.sql("""
    SELECT sensor_id, tran_calc_function, function_parameters
    FROM bmon.bmsapp_sensor
    WHERE function_parameters != ''
    LIMIT 5
""").show()
