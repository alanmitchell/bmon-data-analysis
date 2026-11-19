# The Sensor Reading Database (`bms_data.sqlite`)

This SQLite database holds every sensor reading BMON has stored. It is found in the BMON
project at `bmsapp/readingdb/data/bms_data.sqlite` and is often several gigabytes.

Runnable examples: [`examples/readings.sql`](../examples/readings.sql) and
[`examples/readings.py`](../examples/readings.py).

## Structure

The structure is unusual: there is **one table per sensor**, and the table's name is the
sensor's ID. Every sensor table has the same two columns:

| Column | Type | Description |
|---|---|---|
| `ts` | integer, primary key | Time of the reading as a Unix timestamp: seconds since 1970-01-01 UTC. |
| `val` | real | The reading, in the units given for the sensor in the Django database. |

So there is no "sensor_id" column to filter on. To read a sensor you name its table, and to
read several sensors you query several tables (see [Several sensors](#several-sensors)).

There are also a few tables that are not sensors; their names start with an underscore:

| Table | Contents |
|---|---|
| `_alert_log` | One row for each alert notification BMON sent: `ts` (Unix seconds), `alert_id` (the `id` in `bmsapp_alertcondition`), `sensor_id`, `building`, `message`, `recipients`. The older rows have NULL in `alert_id`, `building` and `recipients`. |
| `_last_raw` | Used internally for counter-type sensors: the last raw count received for a sensor (`id`, `ts`, `val`). |
| `_junk` | An empty table left by BMON's backup routine. |

## Finding a sensor's ID

The names and units of sensors, and the buildings they are in, are in the
[Django database](django-db.md). The `sensors` view joins it all together:

```sql
SELECT building, sensor_group, sensor, sensor_id, unit
FROM sensors
WHERE building ILIKE '%senior center%'
ORDER BY sensor_group, sensor;
```

The text `sensor_id` column is the table name in the reading database. (Don't confuse it
with the integer `id` / `sensor_pk` that the Django database uses internally.)

**A sensor that has never reported has no table.** Querying it gives a "table does not
exist" error. To list only sensors that have data:

```sql
SELECT * FROM sensors
WHERE sensor_id IN (SELECT table_name FROM duckdb_tables() WHERE database_name = 'rd');
```

The reverse also occurs: the reading database can hold tables for sensors that have since
been deleted from the Django database.

## Querying one sensor

In a DuckDB session set up by this project (see the [README](../README.md)), the database
is attached read-only as `rd`.

**The `readings()` macro** is the easy way. It returns the sensor's readings with `ts`
converted to a real timestamp (the original is kept as `ts_unix`):

```sql
SELECT ts, val
FROM readings('A81758FFFE0526D8_temperature')
WHERE ts >= '2026-01-01' AND ts < '2026-02-01'
ORDER BY ts;
```

**The raw table** can be queried too. The table name must be in double quotes, because
sensor IDs start with digits or contain characters such as `.` and `-`:

```sql
SELECT to_timestamp(ts) AS time, val
FROM rd."A81758FFFE0526D8_temperature"
ORDER BY ts DESC
LIMIT 10;
```

`readings()` accepts a quoted ID or a variable (`getvariable('sid')`, see the examples),
but not a column of another table. It cannot be used to loop through sensors in SQL; do
that in Python.

## Time zones

`ts` is a moment in time, with no time zone of its own. `readings()` returns it as a
DuckDB `TIMESTAMP WITH TIME ZONE`, which is *displayed* in the session's time zone and
which interprets a date you type, such as `'2026-01-01'`, in that same time zone. The
session's time zone is your computer's, unless you set it:

```sql
SET TimeZone = 'America/Anchorage';
```

Set it if your computer (or the server you are logged in to) is not in the time zone you
want to think in; servers are often set to UTC. Functions like `date_trunc('day', ts)` and
`hour(ts)` also follow this setting, so it decides where one day ends and the next begins.

## Several sensors

In Python, `bmon_data.sensor_readings()` reads any number of sensors over a date range
into one DataFrame with the columns `sensor_id`, `ts` and `val`:

```python
import bmon_data

conn = bmon_data.connect()
df = bmon_data.sensor_readings(
    conn,
    ["A81758FFFE0526D8_temperature", "A81758FFFE0526D8_co2"],
    start="2026-01-01",
    end="2026-02-01",
)
```

[`examples/readings.py`](../examples/readings.py) shows how to pivot that into one column
per sensor on a common hourly time base.

In SQL, combine sensors with `UNION ALL`:

```sql
SELECT 'living room' AS place, ts, val FROM readings('A81758FFFE0526D8_temperature')
UNION ALL
SELECT 'bedroom' AS place, ts, val FROM readings('A81758FFFE053692_temperature');
```

## Things to know about the values

- Readings arrive at irregular times and different sensors report at different moments.
  To compare sensors, average them into common intervals (`date_trunc('hour', ts)` or
  Pandas `resample`).
- A sensor's values are stored *after* any transform function set for the sensor in the
  Django database, so they are in the units shown in BMON.
- Calculated fields (`is_calculated` in the `sensors` view) are stored in exactly the same
  way as real sensors.
- The largest sensor tables hold tens of millions of rows. Summarize in SQL
  (`GROUP BY`) rather than pulling every reading into Python.

## Be gentle with a live BMON server

Opening the database read-only guarantees a query cannot change the data. It does not make
a query invisible to BMON: while a query is reading a sensor table, SQLite makes writers
wait, and BMON only waits a few seconds before giving up on storing a reading. (This follows
from the way SQLite locking works in the mode BMON uses; it has not been measured on a
running server.)

- Single-sensor queries are quick (well under a second for most sensors, a few seconds for
  the very largest) and are fine.
- For heavy work, such as scanning every sensor table or long-running analysis, copy the
  database file to another location or computer and point this project at the copy with
  the `READING_DB` setting (see [`bmon_data/settings.py`](../bmon_data/settings.py)). BMON
  also keeps compressed backups in `bmsapp/readingdb/data/bak/`.
