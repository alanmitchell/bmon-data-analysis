"""Builds the SQL that connects a DuckDB session to the three BMON data stores.

The same SQL is used in two places, so the Python and CLI experience match:

* bmon_data.connect() runs it on a new in-memory DuckDB connection.
* The 'make-duckdb-init' command writes it to 'bmon_init.sql', which the
  DuckDB CLI runs at startup:   duckdb -init bmon_init.sql

Everything is opened read-only; nothing in this SQL can change BMON's data.
"""
from pathlib import Path

from . import settings


def _quote(path: Path) -> str:
    """Returns 'path' as a SQL string literal."""
    return "'" + str(path).replace("'", "''") + "'"


def store_status() -> dict:
    """Returns a dictionary saying whether each data store was found:
    keys are 'django', 'readings' and 'lora', values are True / False.
    """
    return {
        "django": settings.DJANGO_DB.is_file(),
        "readings": settings.READING_DB.is_file(),
        "lora": settings.LORA_DIR.is_dir() and any(settings.LORA_DIR.glob("*.parquet")),
    }


def init_statements() -> list:
    """Returns a list of (comment, sql) tuples. 'sql' is None for a data store
    that was not found at its configured path; the comment then says so.
    """
    found = store_status()
    stmts = []

    # ---- Django database
    if found["django"]:
        stmts.append((
            "The Django database (buildings, sensors, alerts ...), read-only, as 'bmon'.\n"
            "Tables are referred to as, for example:  bmon.bmsapp_sensor",
            f"ATTACH {_quote(settings.DJANGO_DB)} AS bmon (TYPE sqlite, READ_ONLY);",
        ))
        stmts.append((
            "One row for each sensor in each building, with the names of the\n"
            "building, sensor group and unit filled in. The quickest way to find a sensor_id.",
            """CREATE OR REPLACE VIEW sensors AS
SELECT
    bldg.title      AS building,
    grp.title       AS sensor_group,
    sen.title       AS sensor,
    sen.sensor_id   AS sensor_id,
    unit.label      AS unit,
    sen.is_calculated::BOOLEAN AS is_calculated,
    bldg.id         AS building_pk,
    sen.id          AS sensor_pk
FROM bmon.bmsapp_bldgtosensor AS b2s
JOIN bmon.bmsapp_building    AS bldg ON b2s.building_id = bldg.id
JOIN bmon.bmsapp_sensor      AS sen  ON b2s.sensor_id = sen.id
JOIN bmon.bmsapp_sensorgroup AS grp  ON b2s.sensor_group_id = grp.id
JOIN bmon.bmsapp_unit        AS unit ON sen.unit_id = unit.id;""",
        ))
    else:
        stmts.append((f"Django database NOT FOUND at {settings.DJANGO_DB}", None))

    # ---- Sensor reading database
    if found["readings"]:
        stmts.append((
            "The sensor reading database, read-only, as 'rd'. It has one table per\n"
            "sensor, named with the sensor_id, so a table name must be double-quoted:\n"
            '    SELECT * FROM rd."A81758FFFE0526D8_temperature"\n'
            "Its 'ts' column is a Unix timestamp (integer seconds).",
            f"ATTACH {_quote(settings.READING_DB)} AS rd (TYPE sqlite, READ_ONLY);",
        ))
        stmts.append((
            "readings('sensor_id') returns one sensor's readings with 'ts' converted to a\n"
            "real timestamp; 'ts_unix' keeps the original value.\n"
            "    SELECT * FROM readings('A81758FFFE0526D8_temperature') WHERE ts >= '2026-01-01'",
            """CREATE OR REPLACE MACRO readings(sensor_id) AS TABLE
SELECT to_timestamp(ts) AS ts, val, ts AS ts_unix
FROM query_table('rd.main."' || sensor_id || '"');""",
        ))
        stmts.append((
            "The log of alerts that BMON has sent, with a real timestamp.",
            """CREATE OR REPLACE VIEW alert_log AS
SELECT to_timestamp(ts) AS ts, alert_id, sensor_id, building, message, recipients
FROM rd._alert_log;""",
        ))
    else:
        stmts.append((f"Sensor reading database NOT FOUND at {settings.READING_DB}", None))

    # ---- LoRaWAN gateway diagnostics
    if found["lora"]:
        stmts.append((
            "The LoRaWAN gateway diagnostic data: all of the daily Parquet files\n"
            "presented as one table named 'gateway'.",
            f"CREATE OR REPLACE VIEW gateway AS\n"
            f"SELECT * FROM read_parquet({_quote(settings.LORA_DIR / '*.parquet')});",
        ))
    else:
        stmts.append((f"LoRaWAN Parquet files NOT FOUND in {settings.LORA_DIR}", None))

    return stmts


def init_sql() -> str:
    """Returns the complete text of the DuckDB init file."""
    lines = [
        "-- DuckDB init file for querying BMON data. GENERATED - do not edit.",
        "-- Made by 'uv run make-duckdb-init' from the paths in bmon_data/settings.py;",
        "-- re-run that command if the paths change.",
        "--",
        "-- Use it with:   duckdb -init bmon_init.sql",
        "",
    ]
    for comment, sql in init_statements():
        lines += ["-- " + line for line in comment.splitlines()]
        if sql:
            lines.append(sql)
        lines.append("")
    return "\n".join(lines)


def main():
    """Writes the init file 'bmon_init.sql' into the project directory."""
    out_path = settings.PROJECT_DIR / "bmon_init.sql"
    out_path.write_text(init_sql())
    print(f"Wrote {out_path}\n")
    labels = {
        "django": ("Django database", settings.DJANGO_DB),
        "readings": ("Sensor reading database", settings.READING_DB),
        "lora": ("LoRaWAN Parquet files", settings.LORA_DIR),
    }
    for key, ok in store_status().items():
        label, path = labels[key]
        print(f"  {'found    ' if ok else 'NOT FOUND'}  {label}: {path}")
    print(f"\nStart the DuckDB CLI with:\n  duckdb -init {out_path.name}")


if __name__ == "__main__":
    main()
