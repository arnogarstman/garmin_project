"""Append-only raw landing tables in DuckDB, one table per source: raw.<source>.

A record is only written when it is new or its payload differs from the
latest stored version for the same endpoint and params, so re-fetching an
overlap window does not duplicate unchanged data. Changed payloads are
appended, never updated, so history is kept. Every run is logged in
raw._loads, including runs that found nothing new.
"""

import json
import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from garminreader.ingest.sources.base import RawRecord

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
LOADS_TABLE = "raw._loads"  # leading underscore: can never clash with a source name


@dataclass(frozen=True, slots=True)
class LoadResult:
    load_id: str
    fetched: int
    inserted: int


def _table(source: str) -> str:
    if not _IDENTIFIER.match(source):
        raise ValueError(f"Invalid source name for a table: {source!r}")
    return f"raw.{source}"


def connect(path: Path) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LOADS_TABLE} (
            load_id           VARCHAR     NOT NULL,
            source            VARCHAR     NOT NULL,
            records_fetched   INTEGER     NOT NULL,
            records_inserted  INTEGER     NOT NULL,
            loaded_at         TIMESTAMPTZ NOT NULL
        )
        """
    )
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


def load(con: duckdb.DuckDBPyConnection, source: str, records: Iterable[RawRecord]) -> LoadResult:
    """Write new and changed records in one transaction under a shared
    load_id, and log the run. All or nothing."""
    table = ensure_table(con, source)
    load_id = str(uuid.uuid4())
    loaded_at = datetime.now(UTC)
    batch = [(r.endpoint, json.dumps(r.params, sort_keys=True), json.dumps(r.payload)) for r in records]
    con.begin()
    try:
        con.execute("CREATE OR REPLACE TEMP TABLE _batch (endpoint VARCHAR, params VARCHAR, payload VARCHAR)")
        if batch:
            con.executemany("INSERT INTO _batch VALUES (?, ?, ?)", batch)
        row = con.execute(
            f"""
            INSERT INTO {table}
            SELECT ?, ?, b.endpoint, b.params, b.payload, ?
            FROM _batch AS b
            LEFT JOIN (
                SELECT endpoint, params::VARCHAR AS params, payload::VARCHAR AS payload
                FROM {table}
                QUALIFY row_number() OVER (PARTITION BY endpoint, params::VARCHAR ORDER BY loaded_at DESC) = 1
            ) AS latest USING (endpoint, params)
            WHERE latest.payload IS DISTINCT FROM b.payload
            """,
            [load_id, source, loaded_at],
        ).fetchone()
        inserted = row[0] if row else 0
        con.execute(
            f"INSERT INTO {LOADS_TABLE} VALUES (?, ?, ?, ?, ?)", [load_id, source, len(batch), inserted, loaded_at]
        )
        con.execute("DROP TABLE _batch")
        con.commit()
    except Exception:
        con.rollback()
        raise
    logger.info(
        "Fetched %d records, inserted %d new or changed into %s (load_id=%s)", len(batch), inserted, table, load_id
    )
    return LoadResult(load_id, len(batch), inserted)


def last_loaded_at(con: duckdb.DuckDBPyConnection, source: str) -> datetime | None:
    """When the latest successful load run for this source happened, if any."""
    # Read as naive UTC: returning TIMESTAMPTZ to Python would require pytz.
    row = con.execute(
        f"SELECT max(loaded_at) AT TIME ZONE 'UTC' FROM {LOADS_TABLE} WHERE source = ?", [source]
    ).fetchone()
    return row[0].replace(tzinfo=UTC) if row and row[0] else None
