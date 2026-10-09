"""Append-only raw landing zone (the bronze layer) as tables in the database.

    raw.payloads   one row per stored record: load_id, source, endpoint, params, payload, loaded_at
    raw.loads      one row per load run: the run log, including runs that stored nothing

A record is only written when it is new or its payload differs from the
latest stored version for the same source, endpoint and params, so
re-fetching an overlap window does not duplicate unchanged data. Changed
payloads are appended, never updated, so history is kept. Payloads and
params are stored as JSON exactly as the API returned them.

A load is all or nothing: its records and its run-log row are written in one
transaction, so a run that dies halfway leaves no trace.
"""

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import duckdb

from garminreader import db
from garminreader.ingest.sources.base import RawRecord

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")

_DDL = """
create schema if not exists raw;
create table if not exists raw.payloads (
    load_id varchar not null,
    source varchar not null,
    endpoint varchar not null,
    record_key varchar not null,
    payload_hash varchar not null,
    params json,
    payload json,
    loaded_at timestamptz not null
);
create table if not exists raw.loads (
    load_id varchar primary key,
    source varchar not null,
    records_fetched integer not null,
    records_inserted integer not null,
    loaded_at timestamptz not null
);
"""


@dataclass(frozen=True, slots=True)
class LoadResult:
    load_id: str
    fetched: int
    inserted: int


class RawStore:
    def __init__(self, database: str | None = None) -> None:
        """A store in `database` (default: config.database())."""
        self._database = database

    def load(self, source: str, records: Iterable[RawRecord]) -> LoadResult:
        """Write the new and changed records under one load_id, and log the run. All or nothing."""
        _check_identifier(source)
        batch = list(records)  # drain the source first: if it fails, nothing is written
        load_id = str(uuid.uuid4())
        loaded_at = datetime.now(UTC)

        with self._connect() as con:
            latest = self._latest_hashes(con, source)
            new: dict[str, tuple[str, str, RawRecord]] = {}  # within a batch, the last version of a key wins
            for record in batch:
                _check_identifier(record.endpoint)
                key = _key(record.endpoint, record.params)
                payload_hash = _hash(record.payload)
                if latest.get(key) != payload_hash:
                    new[key] = (key, payload_hash, record)
                    latest[key] = payload_hash
                else:
                    new.pop(key, None)

            rows = [
                (load_id, source, r.endpoint, key, h, json.dumps(r.params), json.dumps(r.payload), loaded_at)
                for key, h, r in new.values()
            ]
            con.begin()
            try:
                if rows:
                    con.executemany("insert into raw.payloads values (?, ?, ?, ?, ?, ?, ?, ?)", rows)
                con.execute(
                    "insert into raw.loads values (?, ?, ?, ?, ?)", [load_id, source, len(batch), len(new), loaded_at]
                )
                con.commit()
            except BaseException:
                con.rollback()
                raise

        logger.info(
            "Fetched %d records, stored %d new or changed for %s (load_id=%s)", len(batch), len(new), source, load_id
        )
        return LoadResult(load_id, len(batch), len(new))

    def last_loaded_at(self, source: str) -> datetime | None:
        """When the latest successful load run for this source happened, if any."""
        _check_identifier(source)
        with self._connect() as con:
            row = con.execute("select max(loaded_at) from raw.loads where source = ?", [source]).fetchone()
        last = row[0] if row else None
        return last.astimezone(UTC) if last else None

    def clear(self, source: str) -> None:
        """Delete every record and run of a source. Only for rebuilding fixture data (the demo)."""
        _check_identifier(source)
        with self._connect() as con:
            con.execute("delete from raw.payloads where source = ?", [source])
            con.execute("delete from raw.loads where source = ?", [source])

    def _connect(self) -> duckdb.DuckDBPyConnection:
        con = db.connect(database=self._database)
        con.execute(_DDL)
        return con

    @staticmethod
    def _latest_hashes(con: duckdb.DuckDBPyConnection, source: str) -> dict[str, str]:
        rows = con.execute(
            """
            select record_key, payload_hash
            from raw.payloads
            where source = ?
            qualify row_number() over (partition by record_key order by loaded_at desc) = 1
            """,
            [source],
        ).fetchall()
        return dict(rows)


def _key(endpoint: str, params: dict[str, Any]) -> str:
    return f"{endpoint}|{json.dumps(params, sort_keys=True)}"


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _check_identifier(name: str) -> None:
    """Source and endpoint names are filtered on in dbt; keep them plain identifiers."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Invalid source or endpoint name: {name!r}")
