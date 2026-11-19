# Using the DuckDB CLI

The [DuckDB command line program](https://duckdb.org/docs/stable/clients/cli/overview)
can query all three BMON data stores in one session, with SQL.

## Starting a session

The connection details are kept in an *init file*, `bmon_init.sql`, which this project
generates from its settings. Make it once (and again whenever the paths in
[`bmon_data/settings.py`](../bmon_data/settings.py) are changed, or a store that was
missing appears):

```bash
uv run make-duckdb-init
```

Then start DuckDB from this project's directory with:

```bash
duckdb -init bmon_init.sql
```

The command prints which stores it found. The paths written into the file are absolute,
so the file works from any directory: `duckdb -init ~/bmon-data-analysis/bmon_init.sql`.

To save typing, add an alias to your `~/.bashrc` (adjust the path), after which the
command `bmonsql` starts a ready-to-use session:

```bash
alias bmonsql='duckdb -init ~/bmon-data-analysis/bmon_init.sql'
```

### What the init file sets up

The session's own database is a temporary in-memory one. The init file adds to it:

| Name | What it is |
|---|---|
| `bmon.<table>` | The [Django database](django-db.md), attached read-only. E.g. `bmon.bmsapp_building`. |
| `sensors` | View: one row per sensor per building, with building, sensor group, sensor title, `sensor_id` and unit. |
| `rd."<sensor_id>"` | The [reading database](reading-db.md), attached read-only. One table per sensor. |
| `readings('<sensor_id>')` | Macro: one sensor's readings, with `ts` as a real timestamp. |
| `alert_log` | View: the alerts BMON has sent, with a real timestamp. |
| `gateway` | View: all the [LoRaWAN diagnostic](lorawan-db.md) Parquet files as one table. |

Open `bmon_init.sql` in an editor to see exactly how each is defined; it is short.

### Why it is safe

- The two SQLite databases are attached with `READ_ONLY`. An `INSERT`, `UPDATE`, `DELETE`
  or `DROP` aimed at them fails with an error.
- The Parquet files are only ever read by `read_parquet()`.
- Tables you create yourself (`CREATE TABLE my_work AS SELECT ...`) go into the temporary
  in-memory database and vanish when you quit. That makes them a good scratch area.

The one thing to avoid is `COPY ... TO` or `.output`/`.once` with a file name inside the
BMON directory; write exported files somewhere else. Also see
["Be gentle with a live BMON server"](reading-db.md#be-gentle-with-a-live-bmon-server)
before running long queries on the reading database.

## The automatic alternative: `~/.duckdbrc`

When started *without* `-init`, the DuckDB CLI runs the commands in the file `~/.duckdbrc`
if it exists. Adding this one line to that file makes every DuckDB session a BMON session:

```
.read /home/me/bmon-data-analysis/bmon_init.sql
```

(Use the full path of your copy.) Because it refers to the generated file instead of
copying it, it stays up to date when `make-duckdb-init` is run again.

This is convenient, but it applies to **every** DuckDB session you start on that computer,
including ones that have nothing to do with BMON, each of which will then open the BMON
databases. The alias above gives the same convenience without that side effect, which is
why it is the recommended approach.

## Finding your way around

```sql
SHOW ALL TABLES;                 -- everything, including the 1000+ sensor tables
SHOW TABLES FROM bmon;           -- the Django database's tables
DESCRIBE bmon.bmsapp_building;   -- the columns of a table
DESCRIBE gateway;
SUMMARIZE gateway;               -- min, max, null count ... of every column
```

Useful CLI commands (they start with a dot and need no semicolon):

| Command | Effect |
|---|---|
| `.help` | List the dot commands. |
| `.read examples/readings.sql` | Run all the SQL in a file. |
| `.timer on` | Show how long each query takes. |
| `.mode csv` / `.mode duckbox` | Switch output to CSV / back to the normal boxes. |
| `.once ~/result.csv` | Send the next query's result to a file (with `.mode csv` first). |
| `.maxrows 200` | Show more rows of a long result. |
| `.quit` | Leave (or press Ctrl-D). |

## Exporting a result

```sql
COPY (
    SELECT ts, val FROM readings('A81758FFFE0526D8_temperature') WHERE ts >= '2026-01-01'
) TO '~/kitchen_temp.csv' (HEADER);

-- or to a Parquet file:
COPY (SELECT * FROM sensors) TO '~/sensors.parquet';
```

## Running one query from the shell

```bash
duckdb -init bmon_init.sql -c "SELECT count(*) FROM gateway"
duckdb -init bmon_init.sql -csv -c "SELECT * FROM sensors" > ~/sensors.csv
```

## Without this project's init file

For reference, these are the read-only connections written out in full, as you would type
them in a plain `duckdb` session started in this project's directory:

```sql
ATTACH '../bmon/bmon.sqlite' AS bmon (TYPE sqlite, READ_ONLY);
ATTACH '../bmon/bmsapp/readingdb/data/bms_data.sqlite' AS rd (TYPE sqlite, READ_ONLY);
SELECT count(*) FROM read_parquet('../bmon/bmsapp/lora_diagnostics/db/gateway/*.parquet');
```

`READ_ONLY` is the important part. (Starting the CLI as `duckdb -readonly some.sqlite` also
opens a single SQLite file read-only.)
