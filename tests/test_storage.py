import json
from pathlib import Path

import pytest

from ingest import storage
from ingest.sources.base import RawRecord


def test_load_keeps_payload_verbatim(tmp_path: Path) -> None:
    payload = {"checkins": [{"id": 1, "nested": {"a": None}}]}
    with storage.connect(tmp_path / "w.duckdb") as con:
        n = storage.load(con, "demo", [RawRecord("checkins", payload, {"page": 0})])
        row = con.execute("SELECT endpoint, params, payload FROM raw.demo").fetchone()
    assert n == 1
    assert row is not None
    assert row[0] == "checkins"
    assert json.loads(row[1]) == {"page": 0}
    assert json.loads(row[2]) == payload


def test_loads_share_a_load_id_and_append(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con:
        storage.load(con, "demo", [RawRecord("a", 1), RawRecord("b", 2)])
        storage.load(con, "demo", [RawRecord("a", 3)])
        ids = con.execute("SELECT load_id, count(*) FROM raw.demo GROUP BY 1 ORDER BY 2").fetchall()
    assert [c for _, c in ids] == [1, 2]


def test_rejects_unsafe_source_name(tmp_path: Path) -> None:
    with storage.connect(tmp_path / "w.duckdb") as con, pytest.raises(ValueError):
        storage.load(con, "x; DROP TABLE y", [])
