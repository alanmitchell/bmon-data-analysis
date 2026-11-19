# bmon-data-analysis

Documentation and sample code for running ad hoc queries on the data in a
[BMON](https://github.com/alanmitchell/bmon) application, with Python or the DuckDB
command line. Everything here opens BMON's data **read-only**.

## The three data stores

| Store | Location in the BMON project | Holds | Documentation |
|---|---|---|---|
| Django database | `bmon.sqlite` | Configuration: buildings, sensors, alerts, dashboards ... | [docs/django-db.md](docs/django-db.md) (with ERD) |
| Sensor reading database | `bmsapp/readingdb/data/bms_data.sqlite` | Every sensor reading; one table per sensor | [docs/reading-db.md](docs/reading-db.md) |
| LoRaWAN gateway diagnostics | `bmsapp/lora_diagnostics/db/gateway/*.parquet` | Signal strength of each LoRaWAN transmission at each gateway | [docs/lorawan-db.md](docs/lorawan-db.md) |

## Setup

You need [uv](https://docs.astral.sh/uv/) for Python and, for command line querying, the
[DuckDB CLI](https://duckdb.org/install/).

1. Clone this project into the folder that contains the BMON project, so the two sit side
   by side:

   ```
   some-folder/
       bmon/
       bmon-data-analysis/
   ```

2. In the `bmon-data-analysis` directory, install the Python packages and generate the
   DuckDB init file:

   ```bash
   uv sync
   uv run make-duckdb-init
   ```

   The second command reports whether each of the three stores was found.

If BMON is somewhere else, or you want to query a *copy* of the data, see the top of
[`bmon_data/settings.py`](bmon_data/settings.py): paths are overridden with a
`settings_local.py` file or environment variables, then `uv run make-duckdb-init` is run
again.

## Querying with the DuckDB CLI

```bash
duckdb -init bmon_init.sql
```

```sql
-- Find sensors (the Django database)
SELECT building, sensor, sensor_id, unit FROM sensors WHERE building ILIKE '%house%';

-- Daily averages of one sensor (the reading database)
SELECT date_trunc('day', ts) AS day, avg(val) AS average
FROM readings('A81758FFFE0526D8_temperature')
WHERE ts >= '2026-01-01'
GROUP BY day ORDER BY day;

-- Average signal strength by gateway (the LoRaWAN Parquet files)
SELECT gateway_id, count(*) AS records, avg(signal_rssi) AS avg_rssi
FROM gateway GROUP BY gateway_id ORDER BY records DESC;
```

More in [docs/duckdb-cli.md](docs/duckdb-cli.md), including what the init file sets up,
exporting results, and using `~/.duckdbrc`.

## Querying with Python

```python
import bmon_data

conn = bmon_data.connect()     # a DuckDB connection with the same setup as the CLI

conn.sql("SELECT * FROM sensors LIMIT 10").show()               # print a result
df = conn.sql("SELECT * FROM gateway WHERE signal_rssi < -115").df()   # Pandas DataFrame

# readings of several sensors over a date range
df = bmon_data.sensor_readings(conn, ["sensor_id_1", "sensor_id_2"], start="2026-01-01")
```

Run a script with `uv run my_script.py`, or start Python with `uv run python`.
`bmon_data.sqlite_django()` and `bmon_data.sqlite_readings()` give read-only connections
using Python's built-in `sqlite3` instead of DuckDB.

## Examples

Each topic has a SQL file for the CLI and a Python script covering similar ground.

| Topic | DuckDB CLI | Python |
|---|---|---|
| Django database | [examples/django_db.sql](examples/django_db.sql) | [examples/django_db.py](examples/django_db.py) |
| Sensor readings | [examples/readings.sql](examples/readings.sql) | [examples/readings.py](examples/readings.py) |
| LoRaWAN diagnostics | [examples/lorawan.sql](examples/lorawan.sql) | [examples/lorawan.py](examples/lorawan.py) |
| Plain `sqlite3`, no DuckDB | | [examples/sqlite3_only.py](examples/sqlite3_only.py) |

```bash
uv run examples/readings.py                                   # a Python example
duckdb -init bmon_init.sql -c ".read examples/readings.sql"   # a SQL example
```

The examples choose sensors from whatever BMON data they find, so they run on any
installation.

## Safety

- **Nothing here can change BMON's data.** The SQLite databases are attached read-only and
  refuse writes; the Parquet files are only read.
- **If you open a database yourself, open it read-only.** A plain
  `sqlite3.connect("bmon.sqlite")` or `duckdb bmon.sqlite` is read/write. The safe forms
  are shown in [examples/sqlite3_only.py](examples/sqlite3_only.py) and at the end of
  [docs/duckdb-cli.md](docs/duckdb-cli.md).
- **On a live server, keep queries of the reading database short**, or work on a copy;
  see [docs/reading-db.md](docs/reading-db.md#be-gentle-with-a-live-bmon-server).
- **Query results can contain personal information** (alert recipients' phone numbers and
  e-mail addresses, user accounts). Take care where exported files end up.

## Keeping the documentation current

[docs/django-db.md](docs/django-db.md) is generated from BMON's `models.py` and the
database schema. After BMON's models change, regenerate it with:

```bash
uv run scripts/make_django_docs.py
```
