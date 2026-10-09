"""Append-only raw landing zone (the bronze layer) as newline-delimited JSON
files, on a local disk or in object storage (anything fsspec can open, such
as abfs:// for Azure Data Lake Storage).

Layout under the root, one directory tree per source:

    <source>/endpoint=<endpoint>/load_date=<YYYY-MM-DD>/<load_id>.jsonl   new or changed records
    _loads/source=<source>/load_date=<YYYY-MM-DD>/<load_id>.json          run log and commit marker
    _state/source=<source>/latest.json                                    change-detection index

A record is only written when it is new or its payload differs from the
latest stored version for the same endpoint and params, so re-fetching an
overlap window does not duplicate unchanged data. Changed payloads are
appended, never updated, so history is kept.

A load is all or nothing: its data files are written first and its _loads
marker last, and readers (dbt) only see records whose load has a marker. A
run that dies halfway leaves invisible files, never half a load. The state
file is an index for speed, not a source of truth: if it is missing it is
rebuilt from the committed files, and if a run dies after its marker but
before the state update, the next run merely re-stores a few unchanged
records, which staging deduplicates anyway.
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

import fsspec
from fsspec.spec import AbstractFileSystem

from garminreader.ingest.sources.base import RawRecord

logger = logging.getLogger(__name__)

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
LOADS_DIR = "_loads"  # leading underscore: can never clash with a source name
STATE_DIR = "_state"


@dataclass(frozen=True, slots=True)
class LoadResult:
    load_id: str
    fetched: int
    inserted: int


@dataclass
class _State:
    last_loaded_at: datetime | None
    hashes: dict[str, str]  # record key -> payload hash of its latest stored version


class RawStore:
    def __init__(self, fs: AbstractFileSystem, root: str) -> None:
        self._fs = fs
        self._root = root.rstrip("/")

    @classmethod
    def from_url(cls, url: str, **storage_options: Any) -> "RawStore":
        """A store at a local path or an fsspec URL such as abfs://raw."""
        fs, root = fsspec.core.url_to_fs(url, **storage_options)
        return cls(fs, root)

    def load(self, source: str, records: Iterable[RawRecord]) -> LoadResult:
        """Write the new and changed records under one load_id, and log the run. All or nothing."""
        _check_identifier(source)
        batch = list(records)  # drain the source first: if it fails, nothing is written
        load_id = str(uuid.uuid4())
        loaded_at = datetime.now(UTC)
        state = self._read_state(source)

        new: dict[str, dict[str, Any]] = {}  # within a batch, the last version of a key wins
        for record in batch:
            _check_identifier(record.endpoint)
            key = _key(record.endpoint, record.params)
            payload_hash = _hash(record.payload)
            if state.hashes.get(key) != payload_hash:
                new[key] = {"endpoint": record.endpoint, "params": record.params, "payload": record.payload}
                state.hashes[key] = payload_hash
            else:
                new.pop(key, None)

        by_endpoint: dict[str, list[dict[str, Any]]] = {}
        for row in new.values():
            by_endpoint.setdefault(row["endpoint"], []).append(row)
        load_date = loaded_at.date().isoformat()
        for endpoint, rows in by_endpoint.items():
            lines = "".join(_jsonl_line(load_id, row, loaded_at) for row in rows)
            self._write(f"{source}/endpoint={endpoint}/load_date={load_date}/{load_id}.jsonl", lines)

        marker = {
            "load_id": load_id,
            "source": source,
            "records_fetched": len(batch),
            "records_inserted": len(new),
            "loaded_at": loaded_at.isoformat(),
        }
        self._write(f"{LOADS_DIR}/source={source}/load_date={load_date}/{load_id}.json", json.dumps(marker))
        state.last_loaded_at = loaded_at
        self._write_state(source, state)

        logger.info(
            "Fetched %d records, stored %d new or changed under %s/%s (load_id=%s)",
            len(batch),
            len(new),
            self._root,
            source,
            load_id,
        )
        return LoadResult(load_id, len(batch), len(new))

    def last_loaded_at(self, source: str) -> datetime | None:
        """When the latest successful load run for this source happened, if any."""
        _check_identifier(source)
        return self._read_state(source).last_loaded_at

    def rebuild_state(self, source: str) -> None:
        """Recompute the change-detection index from the committed raw files."""
        _check_identifier(source)
        self._write_state(source, self._state_from_files(source))

    # -- internals ---------------------------------------------------------

    def _read_state(self, source: str) -> _State:
        path = self._path(f"{STATE_DIR}/source={source}/latest.json")
        if not self._fs.exists(path):
            return self._state_from_files(source)
        with self._fs.open(path, "r") as f:
            data = json.load(f)
        last = data.get("last_loaded_at")
        return _State(datetime.fromisoformat(last) if last else None, data["hashes"])

    def _write_state(self, source: str, state: _State) -> None:
        data = {
            "last_loaded_at": state.last_loaded_at.isoformat() if state.last_loaded_at else None,
            "hashes": state.hashes,
        }
        self._write(f"{STATE_DIR}/source={source}/latest.json", json.dumps(data, sort_keys=True))

    def _state_from_files(self, source: str) -> _State:
        markers = [self._read_json(p) for p in self._fs.glob(self._path(f"{LOADS_DIR}/source={source}/*/*.json"))]
        committed = {m["load_id"]: m["loaded_at"] for m in markers}
        rows: list[tuple[str, str, Any]] = []
        for path in self._fs.glob(self._path(f"{source}/endpoint=*/load_date=*/*.jsonl")):
            endpoint = path.split("endpoint=", 1)[1].split("/", 1)[0]
            with self._fs.open(path, "r") as f:
                for line in f:
                    row = json.loads(line)
                    if row["load_id"] in committed:
                        rows.append((committed[row["load_id"]], _key(endpoint, row["params"]), row["payload"]))
        hashes = {key: _hash(payload) for _, key, payload in sorted(rows, key=lambda r: r[0])}
        last = max(committed.values(), default=None)
        return _State(datetime.fromisoformat(last) if last else None, hashes)

    def _read_json(self, path: str) -> Any:
        with self._fs.open(path, "r") as f:
            return json.load(f)

    def _write(self, relative: str, text: str) -> None:
        path = self._path(relative)
        self._fs.makedirs(path.rsplit("/", 1)[0], exist_ok=True)
        with self._fs.open(path, "w") as f:
            f.write(text)

    def _path(self, relative: str) -> str:
        return f"{self._root}/{relative}"


def _jsonl_line(load_id: str, row: dict[str, Any], loaded_at: datetime) -> str:
    """One stored record. The endpoint is not repeated: it is in the partition path."""
    record = {
        "load_id": load_id,
        "params": row["params"],
        "payload": row["payload"],
        "loaded_at": loaded_at.isoformat(),
    }
    return json.dumps(record) + "\n"


def _key(endpoint: str, params: dict[str, Any]) -> str:
    return f"{endpoint}|{json.dumps(params, sort_keys=True)}"


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _check_identifier(name: str) -> None:
    """Source and endpoint names become directory names that dbt globs over."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Invalid source or endpoint name: {name!r}")
