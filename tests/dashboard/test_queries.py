from datetime import date
from pathlib import Path

import duckdb
import pytest

from garminreader import config
from garminreader.dashboard import queries


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "w.duckdb"
    monkeypatch.setattr(config, "duckdb_path", lambda: path)
    return path


def test_missing_warehouse_is_not_ready(warehouse: Path) -> None:
    with pytest.raises(queries.WarehouseNotReady):
        queries.current_status()


def test_missing_marts_are_not_ready(warehouse: Path) -> None:
    duckdb.connect(str(warehouse)).close()
    with pytest.raises(queries.WarehouseNotReady):
        queries.daily_health(date(2026, 1, 1), date(2026, 1, 2))


def test_daily_health_filters_range_and_exposes_date(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema marts")
        con.execute(
            "create table marts.fct_daily_health as "
            "select * from (values (date '2026-01-01', 50), (date '2026-01-05', 48)) t(calendar_date, resting_hr)"
        )
    df = queries.daily_health(date(2026, 1, 1), date(2026, 1, 2))
    assert list(df.columns) == ["date", "resting_hr"]
    assert df["date"].dt.date.tolist() == [date(2026, 1, 1)]


def test_current_status_maps_nulls_to_none(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema marts")
        con.execute("create table marts.rpt_current_status as select 53.4 as vo2max, null::double as acwr")
    assert queries.current_status() == {"vo2max": 53.4, "acwr": None}
