"""Locations of the three BMON data stores.

By default this project expects to sit next to the BMON project:

    some-folder/
        bmon/                  <- the BMON application
        bmon-data-analysis/    <- this project

so the stores are found under '../bmon/'. If your layout is different, do NOT
edit this file. Instead, override any of the four settings below in one of
these ways (listed from highest to lowest priority):

1. An environment variable with the same name as the setting, prefixed by
   'BMON_' where it isn't already:
       BMON_DIR, BMON_DJANGO_DB, BMON_READING_DB, BMON_LORA_DIR

2. A file named 'settings_local.py' in this directory (it is ignored by git),
   containing lines such as:
       BMON_DIR = "/home/me/bmon-copy"
       READING_DB = "/data/big-disk/bms_data.sqlite"

If only BMON_DIR is overridden, the other three paths follow it.

After changing a setting, re-run 'uv run make-duckdb-init' so the DuckDB CLI
init file, 'bmon_init.sql', picks up the change.
"""
import os
from pathlib import Path

try:
    from . import settings_local as _local
except ImportError:
    _local = None

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _setting(name: str, env_name: str, default: Path) -> Path:
    """Returns the Path for setting 'name', looking first at the environment
    variable 'env_name', then at settings_local.py, then using 'default'.
    """
    value = os.environ.get(env_name) or getattr(_local, name, None) or default
    return Path(value).expanduser().resolve()


# The root directory of the BMON application (the one containing manage.py).
BMON_DIR = _setting("BMON_DIR", "BMON_DIR", PROJECT_DIR.parent / "bmon")

# The Django SQLite database: buildings, sensors, alerts and other configuration.
DJANGO_DB = _setting("DJANGO_DB", "BMON_DJANGO_DB", BMON_DIR / "bmon.sqlite")

# The sensor reading SQLite database: one table of readings per sensor.
READING_DB = _setting(
    "READING_DB", "BMON_READING_DB",
    BMON_DIR / "bmsapp" / "readingdb" / "data" / "bms_data.sqlite",
)

# The directory of LoRaWAN gateway diagnostic Parquet files, one per UTC day.
LORA_DIR = _setting(
    "LORA_DIR", "BMON_LORA_DIR",
    BMON_DIR / "bmsapp" / "lora_diagnostics" / "db" / "gateway",
)
