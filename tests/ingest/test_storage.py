import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pytest

from garminreader.ingest import storage
from garminreader.ingest.sources.base import RawRecord


def _rows(con: duckdb.DuckDBPyConnection) -> list[tuple[Any, ...]]:
    return con.execute("SELECT endpoint, params, payload FROM raw.demo ORDER BY loaded_at, endpoint").fetchall()


def test_load_keeps_payload_verbatim(tmp_path: Path) -> None:
    payload = {"checkins": [{"id": 1, "nested": {"a": None}}]}
    with storage.connect(tmp_path / "w.duckdb") as con:
        result = storage.load(con, "demo", [RawRecord("checkins", payload, {"page": 0})])
        row = con.execute("SELECT endpoint, params, payload FROM raw.demo").fetchone()
    assert (result.fetched, result.inserted) == (1, 1)
    assert row is not None
    assert row[0] == "checkins"
    assert json.loads(row[1]) == {"page": 0}
    assert json.loads(row[2]) == payload


def test_unchanged_records_are_skipped(tmp_path: Path) -> None:
    records = [
        RawRecord("day", {"steps": 1}, {"date": "2026-01-01"}),
        RawRecord("day", {"steps": 2}, {"date": "2026-01-02"}),
    ]
    with storage.connect(tmp_path / "w.duckdb") as con:
        storage.load(con, "demo", records)
        again = storage.load(con, "demo", records)
        assert len(_rows(con)) == 2
    assert (again.fetched, again.inserted) == (2, 0)


def test_changed_records_are_appended(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con:
        storage.load(con, "demo", [RawRecord("day", {"steps": 1}, {"date": "2026-01-01"})])
        changed = storage.load(con, "demo", [RawRecord("day", {"steps": 5}, {"date": "2026-01-01"})])
        assert [json.loads(r[2]) for r in _rows(con)] == [{"steps": 1}, {"steps": 5}]
    assert changed.inserted == 1


def test_value_changing_back_is_recorded(tmp_path: Path) -> None:
    """Compared against the latest version only, so A -> B -> A keeps all three."""
    with storage.connect(tmp_path / "w.duckdb") as con:
        for steps in (1, 2, 1):
            storage.load(con, "demo", [RawRecord("day", {"steps": steps}, {"date": "2026-01-01"})])
        assert len(_rows(con)) == 3


def test_params_key_order_does_not_matter(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con:
        storage.load(con, "demo", [RawRecord("range", 1, {"a": 1, "b": 2})])
        again = storage.load(con, "demo", [RawRecord("range", 1, {"b": 2, "a": 1})])
    assert again.inserted == 0


def test_every_run_is_logged(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con:
        storage.load(con, "demo", [RawRecord("a", 1)])
        storage.load(con, "demo", [RawRecord("a", 1)])
        log = con.execute("SELECT records_fetched, records_inserted FROM raw._loads ORDER BY loaded_at").fetchall()
    assert log == [(1, 1), (1, 0)]


def test_failed_load_writes_nothing(tmp_path: Path) -> None:
    def broken() -> Any:
        yield RawRecord("a", 1)
        raise RuntimeError("source died")

    with storage.connect(tmp_path / "w.duckdb") as con:
        with pytest.raises(RuntimeError):
            storage.load(con, "demo", broken())
        assert con.execute("SELECT count(*) FROM raw._loads").fetchone() == (0,)


def test_rejects_unsafe_source_name(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con, pytest.raises(ValueError):
        storage.load(con, "x; DROP TABLE y", [])


def test_last_loaded_at_advances_even_without_new_data(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con:
        assert storage.last_loaded_at(con, "demo") is None
        storage.load(con, "demo", [RawRecord("a", 1)])
        first = storage.last_loaded_at(con, "demo")
        storage.load(con, "demo", [RawRecord("a", 1)])
        second = storage.last_loaded_at(con, "demo")
        assert storage.last_loaded_at(con, "other") is None
    assert first is not None and second is not None
    assert first < second <= datetime.now(UTC)
