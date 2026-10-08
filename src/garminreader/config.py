"""Settings from the environment (.env in the project root)."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(PROJECT_ROOT / ".env")


def duckdb_path() -> Path:
    return Path(os.getenv("DUCKDB_PATH", PROJECT_ROOT / "data" / "warehouse.duckdb"))


def garmin_token_dir() -> Path:
    return Path(os.getenv("GARMIN_TOKEN_DIR", PROJECT_ROOT / ".garmin_tokens"))


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required setting {key}; add it to .env")
    return value


def optional_env(key: str) -> str | None:
    return os.getenv(key) or None
