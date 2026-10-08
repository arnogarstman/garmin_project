"""Settings from the environment (.env in the project root)."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def _project_path(key: str, default: str) -> Path:
    """A path setting; relative values resolve against the project root."""
    return PROJECT_ROOT / os.getenv(key, default)


def duckdb_path() -> Path:
    return _project_path("DUCKDB_PATH", "data/warehouse.duckdb")


def garmin_token_dir() -> Path:
    return _project_path("GARMIN_TOKEN_DIR", ".garmin_tokens")


def dbt_project_dir() -> Path:
    return PROJECT_ROOT / "transform"


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required setting {key}; add it to .env")
    return value


def optional_env(key: str) -> str | None:
    return os.getenv(key) or None
