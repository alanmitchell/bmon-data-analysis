# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Purpose

Documentation and sample code that let people run **ad hoc, read-only queries** on the data
of a [BMON](https://github.com/alanmitchell/bmon) application (a Django building-monitoring
app). The audience has basic Python skills and also uses the DuckDB CLI. Goals, in order:
harmless to BMON's data, easy to use, clear to read. Favor plain, well-commented code and
plain-language docs over cleverness or abstraction.

This project is cloned next to the BMON project, so BMON is normally at `../bmon/`.

## The three data stores (all inside the BMON project)

| Store | Path under `../bmon/` | Notes |
|---|---|---|
| Django DB | `bmon.sqlite` | Config. Tables `bmsapp_*`, from `bmsapp/models.py`. |
| Reading DB | `bmsapp/readingdb/data/bms_data.sqlite` | One table per sensor, named by `sensor_id`, columns `(ts integer Unix seconds, val real)`. Plus `_alert_log`, `_last_raw`. Multi-GB. |
| LoRaWAN diagnostics | `bmsapp/lora_diagnostics/db/gateway/YYYY-MM-DD.parquet` | One file per UTC day; one row per gateway per uplink. Written by BMON's `bmsapp/lora_diagnostics/store.py`. |

## Hard rule: never write to BMON's data

- Open SQLite only read-only: DuckDB `ATTACH '...' (TYPE sqlite, READ_ONLY)`, or
  `sqlite3.connect("file:...?mode=ro", uri=True)`. Never a bare `sqlite3.connect(path)` or
  `duckdb <file>`.
- Never create, modify or delete files inside `../bmon/`, and do not run BMON's code,
  `manage.py`, or migrations from here.
- Every example and doc snippet must show the read-only form.
- Read-only is not zero-impact: both SQLite files use rollback-journal mode, so a long
  read can make BMON's writers time out on a live server. Avoid long scans of the whole
  reading DB (counting rows in every table took over 3 minutes locally).

## Layout

- `bmon_data/settings.py` — the four paths (`BMON_DIR`, `DJANGO_DB`, `READING_DB`,
  `LORA_DIR`). Overridden by env vars (`BMON_DIR`, `BMON_DJANGO_DB`, `BMON_READING_DB`,
  `BMON_LORA_DIR`) or a git-ignored `bmon_data/settings_local.py`. Don't hard-code paths
  anywhere else.
- `bmon_data/duckdb_init.py` — **single source of the DuckDB setup SQL** (attaches, the
  `sensors`, `alert_log` and `gateway` views, the `readings()` macro). Used both by
  `bmon_data.connect()` and by the `make-duckdb-init` command, which writes
  `bmon_init.sql`. Change the setup here only, so Python and the CLI stay identical.
- `bmon_data/__init__.py` — `connect()`, `sensor_readings()`, `sqlite_django()`,
  `sqlite_readings()`.
- `bmon_init.sql` — generated, git-ignored, contains absolute local paths. Never commit or
  hand-edit; regenerate with `uv run make-duckdb-init`.
- `docs/django-db.md` — **generated** by `scripts/make_django_docs.py` (Mermaid ERD + table
  descriptions from the DB schema and the comments in BMON's `models.py`). Edit the script,
  not the file.
- `docs/reading-db.md`, `docs/lorawan-db.md`, `docs/duckdb-cli.md` — hand-written.
- `examples/` — paired `.sql` (CLI) and `.py` examples per store, plus `sqlite3_only.py`.

## Commands

```bash
uv sync                                  # install dependencies
uv run make-duckdb-init                  # (re)generate bmon_init.sql; reports stores found
duckdb -init bmon_init.sql               # CLI session with everything attached
uv run examples/readings.py              # run a Python example
duckdb -init bmon_init.sql -c ".read examples/readings.sql"   # run a SQL example
uv run scripts/make_django_docs.py       # regenerate docs/django-db.md
```

There is no test suite. After changing the setup SQL, helpers or examples, run all four
Python examples and all three `.sql` files and check for errors.

## Things that are easy to get wrong

- **Two sensor IDs.** `bmsapp_sensor.id` is the integer key used by foreign keys inside the
  Django DB (confusingly, in columns named `sensor_id`). `bmsapp_sensor.sensor_id` is the
  text ID that names the reading-DB table. LoRaWAN sensor IDs are `<device_eui>_<field>`,
  which is how the Parquet data joins to sensors.
- **Reading-DB table names need double quotes** (`rd."75945"`); many start with digits or
  contain `.`/`-`. A sensor that has never reported has no table.
- `readings()` uses `query_table()`, which takes only a literal or `getvariable()`, not a
  column, so it cannot be used in a lateral join. Loop over sensors in Python instead.
- **Examples must not hard-code sensor IDs, EUIs or building names as required inputs.**
  They select them from the data so they run on any BMON installation.
- **DuckDB version spread.** BMON pins the Python `duckdb` package to 1.2; this project and
  the CLI may be 2.x. Keep to features in both. In DuckDB 2.x a relation from `conn.sql()`
  has no `fetchone()`, and `conn.execute().fetchone()` leaves a pending result that blocks
  the next query; use `conn.sql(...).fetchall()` / `.df()` / `.show()` and pass parameters
  with `conn.sql(sql, params=[...])`.
- `pytz` is a dependency because DuckDB needs it to return `TIMESTAMPTZ` values through
  `fetchall()`.
- Timestamps display in the session time zone (`SET TimeZone = '...'`); Parquet day files
  are split on UTC days.
- Query results can include personal data (alert recipients, `auth_user`). Don't paste
  real phone numbers, e-mail addresses or message contents into docs or examples.
- The local `../bmon` data may be a development copy: its Django DB need not match the
  Parquet sample files, so the gateway-to-building join can legitimately return no rows.
