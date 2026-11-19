"""Read-only access to the data stores of a BMON application.

    import bmon_data

    conn = bmon_data.connect()          # DuckDB, all three stores
    conn.sql("SELECT * FROM sensors LIMIT 10").show()
    df = conn.sql("SELECT * FROM readings('my_sensor_id')").df()

See connect() for what is available on the connection. The paths to the
stores are set in bmon_data/settings.py.
"""
import sqlite3
import warnings
from datetime import datetime
from pathlib import Path

import duckdb

from . import settings
from .duckdb_init import init_statements, store_status

__all__ = [
    "settings", "connect", "sensor_readings",
    "sqlite_django", "sqlite_readings", "store_status",
]


def connect() -> duckdb.DuckDBPyConnection:
    """Returns an in-memory DuckDB connection set up to query all the BMON
    data. All of the stores are opened read-only, so no query can change
    BMON's data. Available on the connection:

    bmon.<table>       the Django database tables, e.g. bmon.bmsapp_building
    sensors            view: every sensor in every building, with names
    rd."<sensor_id>"   the raw reading table of a sensor (ts is Unix seconds)
    readings('<id>')   one sensor's readings with a real timestamp
    alert_log          view: the alerts BMON has sent
    gateway            view: the LoRaWAN gateway diagnostic records

    A store that is not found at its configured path is skipped with a warning.
    """
    conn = duckdb.connect()      # in-memory; holds only the views and macros
    for comment, sql in init_statements():
        if sql is None:
            warnings.warn(comment, stacklevel=2)
        else:
            conn.execute(sql)
    return conn


def _to_unix(when) -> int:
    """Converts a datetime, a date/time string like '2026-01-15' or
    '2026-01-15 14:30', or a Unix timestamp into integer Unix seconds. Strings
    and datetimes without a time zone are taken to be in this computer's
    local time zone.
    """
    if isinstance(when, (int, float)):
        return int(when)
    if isinstance(when, str):
        when = datetime.fromisoformat(when)
    return int(when.timestamp())


def sensor_readings(conn, sensor_ids, start=None, end=None):
    """Returns a Pandas DataFrame of sensor readings in long format, with the
    columns 'sensor_id', 'ts' and 'val', ordered by sensor and time.

    conn:        a connection from connect()
    sensor_ids:  one sensor_id, or a list of them
    start, end:  optional limits on the reading time; 'start' is included and
                 'end' is not. Each can be a string such as '2026-01-15' or
                 '2026-01-15 14:30', a datetime, or a Unix timestamp.
    """
    if isinstance(sensor_ids, str):
        sensor_ids = [sensor_ids]

    # Filtering on the raw integer timestamp lets SQLite use the table's index.
    conditions = []
    if start is not None:
        conditions.append(f"ts >= {_to_unix(start)}")
    if end is not None:
        conditions.append(f"ts < {_to_unix(end)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    selects = []
    for sensor_id in sensor_ids:
        table = '"' + sensor_id.replace('"', '""') + '"'
        literal = "'" + sensor_id.replace("'", "''") + "'"
        selects.append(
            f"SELECT {literal} AS sensor_id, to_timestamp(ts) AS ts, val FROM rd.{table} {where}"
        )
    sql = " UNION ALL ".join(selects) + " ORDER BY sensor_id, ts"
    return conn.sql(sql).df()


def _sqlite_read_only(path: Path) -> sqlite3.Connection:
    """Returns a read-only sqlite3 connection to the database file 'path'."""
    # The 'mode=ro' URI is what makes the connection read-only; without it,
    # sqlite3.connect() opens the file read/write (and creates a missing file).
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def sqlite_django() -> sqlite3.Connection:
    """Returns a read-only connection to the Django database, using Python's
    built-in sqlite3 module instead of DuckDB.
    """
    return _sqlite_read_only(settings.DJANGO_DB)


def sqlite_readings() -> sqlite3.Connection:
    """Returns a read-only connection to the sensor reading database, using
    Python's built-in sqlite3 module instead of DuckDB.
    """
    return _sqlite_read_only(settings.READING_DB)
