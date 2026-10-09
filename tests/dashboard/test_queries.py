from datetime import date
from pathlib import Path

import duckdb
import pytest

from garminreader import config
from garminreader.dashboard import queries


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "w.duckdb"
    monkeypatch.setattr(config, "database", lambda: str(path))
    return path


def test_missing_warehouse_is_not_ready(warehouse: Path) -> None:
    """Querying before the warehouse file exists raises WarehouseNotReady.

    The dashboard catches this error to tell the user to run ingest and transform first,
    instead of crashing.
    """
    with pytest.raises(queries.WarehouseNotReady):
        queries.current_status()


def test_missing_marts_are_not_ready(warehouse: Path) -> None:
    """A warehouse without marts (dbt has not run yet) also raises WarehouseNotReady.

    DuckDB's CatalogException for the missing table is translated, so the dashboard handles a
    missing file and missing tables the same way.
    """
    duckdb.connect(str(warehouse)).close()
    with pytest.raises(queries.WarehouseNotReady):
        queries.daily_health(date(2026, 1, 1), date(2026, 1, 2))


def test_daily_health_filters_range_and_exposes_date(warehouse: Path) -> None:
    """daily_health() returns only rows between start and end (inclusive), with a `date` column.

    The 2026-01-05 row lies outside the requested range and must be dropped. calendar_date is
    exposed as `date` (a timestamp, which the charts expect) and every other column passes
    through unchanged.
    """
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
    """current_status() returns the single status row as a dict, with SQL NULLs as None.

    The dashboard checks for None to show a placeholder for metrics the device has not
    reported, so NULLs must not leak through as NaN.
    """
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema marts")
        con.execute("create table marts.rpt_current_status as select 53.4 as vo2max, null::double as acwr")
    assert queries.current_status() == {"vo2max": 53.4, "acwr": None}


def test_heart_rate_zones_prefer_the_default_sport(warehouse: Path) -> None:
    """With zones for several sports, the DEFAULT set is returned; it applies to every sport without its own."""
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema marts")
        con.execute(
            "create table marts.rpt_heart_rate_zones as "
            "select * from (values ('CYCLING', 110), ('DEFAULT', 116)) t(sport, zone_2_floor_bpm)"
        )
    assert queries.heart_rate_zones() == {"sport": "DEFAULT", "zone_2_floor_bpm": 116}


def test_race_results_cover_all_time_with_a_date_column(warehouse: Path) -> None:
    """Race results are not filtered by the dashboard's date range, oldest first, with race_date exposed as `date`.

    Progression only makes sense against the full history of results.
    """
    with duckdb.connect(str(warehouse)) as con:
        con.execute("create schema marts")
        con.execute(
            "create table marts.fct_race_results as select * from (values "
            "(2, date '2026-04-05', 6100), (1, date '2019-04-07', 6600)) t(activity_id, race_date, finish_time_s)"
        )
    df = queries.race_results()
    assert df["activity_id"].tolist() == [1, 2]
    assert "date" in df.columns and "race_date" not in df.columns
