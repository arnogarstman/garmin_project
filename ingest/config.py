"""Settings from the environment (.env in the project root)."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def duckdb_path() -> Path:
    return Path(os.getenv("DUCKDB_PATH", PROJECT_ROOT / "data" / "warehouse.duckdb"))


def require_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(f"Missing required setting {key}; add it to .env")
    return value
