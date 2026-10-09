import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from garminreader.ingest import storage
from garminreader.ingest.sources.base import RawRecord


def _store(tmp_path: Path) -> storage.RawStore:
    return storage.RawStore.from_url(str(tmp_path / "raw"))


def _rows(tmp_path: Path, source: str = "demo") -> list[dict[str, Any]]:
    """Every stored record of the source, oldest load first, with its endpoint from the partition path."""
    rows = []
    for path in (tmp_path / "raw" / source).glob("endpoint=*/load_date=*/*.jsonl"):
        endpoint = path.parts[-3].removeprefix("endpoint=")
        rows += [json.loads(line) | {"endpoint": endpoint} for line in path.read_text().splitlines()]
    return sorted(rows, key=lambda r: (r["loaded_at"], r["endpoint"]))


def _markers(tmp_path: Path, source: str = "demo") -> list[dict[str, Any]]:
    markers = [json.loads(p.read_text()) for p in (tmp_path / "raw" / "_loads").glob(f"source={source}/*/*.json")]
    return sorted(markers, key=lambda m: m["loaded_at"])


def test_load_keeps_payload_verbatim(tmp_path: Path) -> None:
    """The raw layer stores the API response exactly as received.

    Nested objects and nulls must survive the round trip into the raw files unchanged, and
    the params are stored next to the payload, partitioned by endpoint and load date. All
    parsing happens later in dbt, never here.
    """
    payload = {"checkins": [{"id": 1, "nested": {"a": None}}]}
    result = _store(tmp_path).load("demo", [RawRecord("checkins", payload, {"page": 0})])
    [row] = _rows(tmp_path)
    assert (result.fetched, result.inserted) == (1, 1)
    assert row["endpoint"] == "checkins"
    assert row["params"] == {"page": 0}
    assert row["payload"] == payload
    today = datetime.now(UTC).date().isoformat()
    assert (tmp_path / "raw" / "demo" / "endpoint=checkins" / f"load_date={today}" / f"{result.load_id}.jsonl").exists()


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
    assert [(r["params"], r["payload"]) for r in _rows(tmp_path)] == [(r.params, r.payload) for r in records]


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


def test_every_run_is_logged(tmp_path: Path) -> None:
    """Each load run writes one marker to _loads, including runs that stored nothing.

    The marker holds fetched and stored counts per run, so a run that found no changes is
    still visible as (fetched=1, inserted=0) rather than leaving no trace.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("a", 1)])
    store.load("demo", [RawRecord("a", 1)])
    assert [(m["records_fetched"], m["records_inserted"]) for m in _markers(tmp_path)] == [(1, 1), (1, 0)]


def test_failed_load_writes_nothing(tmp_path: Path) -> None:
    """A source that fails partway through leaves no files at all.

    The fake source yields one record and then raises. The error must propagate, and since
    the source is drained before anything is written, there is no data file and no marker. A
    logged half-finished run would move the resume point forward, and the next ingest would
    silently skip the data that was never loaded.
    """

    def broken() -> Any:
        yield RawRecord("a", 1)
        raise RuntimeError("source died")

    with pytest.raises(RuntimeError):
        _store(tmp_path).load("demo", broken())
    assert not (tmp_path / "raw").exists() or not any((tmp_path / "raw").rglob("*.json*"))


def test_files_without_a_marker_are_not_committed(tmp_path: Path) -> None:
    """Data files of a load that never wrote its marker do not count as stored.

    This is the crash case between writing data and writing the marker: dbt ignores such
    records, and so must change detection, or the next run would skip re-storing them.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})])
    orphan = tmp_path / "raw" / "demo" / "endpoint=day" / "load_date=2026-01-02" / "dead-load.jsonl"
    orphan.parent.mkdir(parents=True)
    orphan.write_text(json.dumps({"load_id": "dead-load", "params": {"date": "2026-01-01"}, "payload": {"steps": 9}}))
    (tmp_path / "raw" / "_state").rename(tmp_path / "state-gone")  # force a rebuild from the files

    again = store.load("demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})])
    assert again.inserted == 0  # the committed version {"steps": 1} is the latest, not the orphan


def test_state_is_rebuilt_from_raw_files(tmp_path: Path) -> None:
    """Without its index, the store recomputes change detection and the resume point from the raw files.

    The raw files are the source of truth; the index only saves reading them on every run.
    """
    store = _store(tmp_path)
    store.load("demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})])
    last = store.last_loaded_at("demo")
    for state_file in (tmp_path / "raw" / "_state").rglob("*.json"):
        state_file.unlink()
    assert store.last_loaded_at("demo") == last
    assert store.load("demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})]).inserted == 0


def test_rejects_unsafe_names(tmp_path: Path) -> None:
    """Source and endpoint names become directories that dbt globs over, so anything but a plain identifier fails."""
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
