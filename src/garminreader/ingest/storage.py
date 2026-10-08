"""Append-only raw landing tables in DuckDB, one table per source: raw.<source>."""

import json
import logging
import re
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from garminreader.ingest.sources.base import RawRecord

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")


def _table(source: str) -> str:
    if not _IDENTIFIER.match(source):
        raise ValueError(f"Invalid source name for a table: {source!r}")
    return f"raw.{source}"


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    return con


def ensure_table(con: duckdb.DuckDBPyConnection, source: str) -> str:
    table = _table(source)
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table} (
            load_id     VARCHAR     NOT NULL,
            source      VARCHAR     NOT NULL,
            endpoint    VARCHAR     NOT NULL,
            params      JSON,
            payload     JSON,
            loaded_at   TIMESTAMPTZ NOT NULL
        )
        """
    )
    return table


def load(con: duckdb.DuckDBPyConnection, source: str, records: Iterable[RawRecord]) -> int:
    """Write all records in one transaction under a shared load_id.
    Returns the row count. Deduplication is left to dbt."""
    table = ensure_table(con, source)
    load_id = str(uuid.uuid4())
    loaded_at = datetime.now(UTC)
    rows = [(load_id, source, r.endpoint, json.dumps(r.params), json.dumps(r.payload), loaded_at) for r in records]
    con.begin()
    try:
        if rows:
            con.executemany(f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?, ?)", rows)
        con.commit()
    except Exception:
        con.rollback()
        raise
    logger.info("Loaded %d records into %s (load_id=%s)", len(rows), table, load_id)
    return len(rows)
