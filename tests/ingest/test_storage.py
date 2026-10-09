import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from garminreader.ingest import storage
from garminreader.ingest.sources.base import RawRecord


def _db(tmp_path: Path) -> str:
    return str(tmp_path / "w.duckdb")


def _store(tmp_path: Path) -> storage.RawStore:
    return storage.RawStore(_db(tmp_path))


def _query(tmp_path: Path, sql: str) -> list[tuple[Any, ...]]:
    with duckdb.connect(_db(tmp_path), read_only=True) as con:
        return con.execute(sql).fetchall()


def _rows(tmp_path: Path, source: str = "demo") -> list[dict[str, Any]]:
    """Every stored record of the source, oldest load first, with params and payload parsed."""
    rows = _query(
        tmp_path,
        f"select load_id, endpoint, params, payload from raw.payloads where source = '{source}' order by loaded_at",
    )
    return [{"load_id": r[0], "endpoint": r[1], "params": json.loads(r[2]), "payload": json.loads(r[3])} for r in rows]


def test_load_keeps_payload_verbatim(tmp_path: Path) -> None:
    """The raw layer stores the API response exactly as received.

    Nested objects and nulls must survive the round trip into the raw table unchanged, and
    the params are stored next to the payload with the endpoint. All parsing happens later in
    dbt, never here.
    """
    payload = {"checkins": [{"id": 1, "nested": {"a": None}}]}
    result = _store(tmp_path).load("demo", [RawRecord("checkins", payload, {"page": 0})])
    [row] = _rows(tmp_path)
    assert (result.fetched, result.inserted) == (1, 1)
    assert row == {"load_id": result.load_id, "endpoint": "checkins", "params": {"page": 0}, "payload": payload}


def test_unchanged_records_are_skipped(tmp_path: Path) -> None:
    """Loading the same records twice stores them only once.

    Every ingest re-fetches an overlap window (the resume point minus 1 day), so identical
    records arrive again. They count as fetched but are not stored a second time.
    """
    records = [
        RawRecord("day", {"steps": 1}, {"date": "2026-01-01"}),
        RawRecord("day", {"steps": 2}, {"date": "2026-01-02"}),
    ]
    store = _store(tmp_path)
    store.load("demo", records)
    again = store.load("demo", records)
    assert (again.fetched, again.inserted) == (2, 0)
    assert sorted((str(r["params"]), str(r["payload"])) for r in _rows(tmp_path)) == sorted(
        (str(r.params), str(r.payload)) for r in records
    )


def test_changed_records_are_appended(tmp_path: Path) -> None:
    """A new payload for the same endpoint and params is appended as an extra record.

    The old version is kept rather than updated in place, so the raw layer holds the full
    history. Staging models then pick the newest version.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})])
    changed = store.load("demo", [RawRecord("day", {"steps": 5}, {"date": "2026-01-01"})])
    assert changed.inserted == 1
    assert [r["payload"] for r in _rows(tmp_path)] == [{"steps": 1}, {"steps": 5}]


def test_value_changing_back_is_recorded(tmp_path: Path) -> None:
    """A payload that changes and then reverts (A, then B, then A) is stored three times.

    Change detection compares against the latest stored version only, not against every version
    ever seen. Reverting to an earlier value is therefore a real change, and the newest record
    correctly reflects the current state.
    """
    store = _store(tmp_path)
    for steps in (1, 2, 1):
        store.load("demo", [RawRecord("day", {"steps": steps}, {"date": "2026-01-01"})])
    assert len(_rows(tmp_path)) == 3


def test_params_key_order_does_not_matter(tmp_path: Path) -> None:
    """Params that differ only in key order identify the same record.

    Params are part of a record's identity and are compared with sorted keys, so
    {"a": 1, "b": 2} and {"b": 2, "a": 1} match and the second load stores nothing.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("range", 1, {"a": 1, "b": 2})])
    assert store.load("demo", [RawRecord("range", 1, {"b": 2, "a": 1})]).inserted == 0


def test_sources_do_not_share_change_detection(tmp_path: Path) -> None:
    """The same endpoint and params under another source is a different record."""
    store = _store(tmp_path)
    store.load("demo", [RawRecord("day", 1, {"date": "2026-01-01"})])
    assert store.load("other", [RawRecord("day", 1, {"date": "2026-01-01"})]).inserted == 1


def test_every_run_is_logged(tmp_path: Path) -> None:
    """Each load run writes one row to raw.loads, including runs that stored nothing.

    The row holds fetched and stored counts per run, so a run that found no changes is
    still visible as (fetched=1, inserted=0) rather than leaving no trace.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("a", 1)])
    store.load("demo", [RawRecord("a", 1)])
    logged = _query(tmp_path, "select records_fetched, records_inserted from raw.loads order by loaded_at")
    assert logged == [(1, 1), (1, 0)]


def test_failed_load_writes_nothing(tmp_path: Path) -> None:
    """A source that fails partway through leaves no records and no run-log row.

    The fake source yields one record and then raises. The error must propagate, and since
    the source is drained before anything is written, nothing is stored. A logged
    half-finished run would move the resume point forward, and the next ingest would
    silently skip the data that was never loaded.
    """

    def broken() -> Any:
        yield RawRecord("a", 1)
        raise RuntimeError("source died")

    store = _store(tmp_path)
    with pytest.raises(RuntimeError):
        store.load("demo", broken())
    assert store.last_loaded_at("demo") is None
    assert _rows(tmp_path) == []


def test_clear_removes_one_source_only(tmp_path: Path) -> None:
    """Rebuilding the demo fixture clears its own source and leaves others untouched."""
    store = _store(tmp_path)
    store.load("demo", [RawRecord("a", 1)])
    store.load("other", [RawRecord("a", 1)])
    store.clear("demo")
    assert store.last_loaded_at("demo") is None
    assert _rows(tmp_path, "demo") == []
    assert len(_rows(tmp_path, "other")) == 1


def test_rejects_unsafe_names(tmp_path: Path) -> None:
    """Source and endpoint names are plain identifiers, so anything else fails before writing."""
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.load("../etc", [])
    with pytest.raises(ValueError):
        store.load("demo", [RawRecord("a/b", 1)])


def test_last_loaded_at_advances_even_without_new_data(tmp_path: Path) -> None:
    """last_loaded_at() returns the time of the latest run, whether or not it stored records.

    It is None before the first load and is tracked per source. Ingest resumes from this
    timestamp, so it comes from the run log rather than the newest stored record. Otherwise
    a period without changes would keep the resume point in the past and make every ingest
    re-fetch an ever larger window.
    """
    store = _store(tmp_path)
    assert store.last_loaded_at("demo") is None
    store.load("demo", [RawRecord("a", 1)])
    first = store.last_loaded_at("demo")
    store.load("demo", [RawRecord("a", 1)])
    second = store.last_loaded_at("demo")
    assert store.last_loaded_at("other") is None
    assert first is not None and second is not None
    assert first < second <= datetime.now(UTC)
