"""Settings from the environment (.env in the project root)."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")

DataProfile = Literal["prod", "demo"]


def data_profile() -> DataProfile:
    """prod: your own Garmin data. demo: the synthetic athlete, safe to publish."""
    profile = os.getenv("DATA_PROFILE", "prod")
    if profile not in ("prod", "demo"):
        raise RuntimeError(f"DATA_PROFILE must be prod or demo, not {profile!r}")
    return "demo" if profile == "demo" else "prod"


def is_demo() -> bool:
    return data_profile() == "demo"


def _profile_setting(key: str, default: str) -> str:
    """A data location for the active profile. The demo reads DEMO_<key> and never
    the prod key: the demo is rebuilt from scratch, so a prod setting must never be
    able to point it at real data. Relative paths resolve against the project root."""
    demo = is_demo()
    value = os.getenv(f"DEMO_{key}" if demo else key) or f"data/{'demo/' if demo else ''}{default}"
    if "://" in value:
        return value
    return str(PROJECT_ROOT / value)


def duckdb_path() -> Path:
    """The local DuckDB file dbt builds and the dashboard reads."""
    return Path(_profile_setting("DUCKDB_PATH", "warehouse.duckdb"))


def raw_root() -> str:
    """Where raw files land (the bronze layer): a local directory, or an fsspec
    URL such as abfs://raw for Azure Data Lake Storage."""
    return _profile_setting("RAW_ROOT", "raw")


def warehouse_url() -> str | None:
    """Object storage location the built warehouse is published to and the
    dashboard reads from, e.g. abfs://warehouse/warehouse.duckdb. Unset locally."""
    return os.getenv("DEMO_WAREHOUSE_URL" if is_demo() else "WAREHOUSE_URL") or None


def goal_path() -> str:
    """Where the training goal is saved: a local path, or an fsspec URL in the
    cloud, where container disks do not survive a restart."""
    return _profile_setting("GOAL_PATH", "goal.json")


def history_start() -> str:
    """First day of the Dagster daily partitions for real data (YYYY-MM-DD)."""
    return os.getenv("GARMIN_HISTORY_START", "2026-01-01")


def garmin_token_dir() -> Path:
    return PROJECT_ROOT / os.getenv("GARMIN_TOKEN_DIR", ".garmin_tokens")


def dbt_project_dir() -> Path:
    return PROJECT_ROOT / "transform"


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required setting {key}; add it to .env")
    return value


def optional_env(key: str) -> str | None:
    return os.getenv(key) or None
