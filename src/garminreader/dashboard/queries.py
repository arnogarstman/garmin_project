"""Read-only access to the dbt marts. The dashboard's only database access.

Columns are aliased to the names the dashboard modules use.
"""

from datetime import date, datetime
from typing import Any

import duckdb
import pandas as pd

from garminreader import config, warehouse


class WarehouseNotReady(RuntimeError):
    """The warehouse file or the marts do not exist yet."""


def _connect() -> duckdb.DuckDBPyConnection:
    path = config.duckdb_path()
    url = config.warehouse_url()
    if url:
        try:
            warehouse.sync_local_copy(url, path)
        except FileNotFoundError as exc:
            raise WarehouseNotReady(f"No published warehouse at {url}") from exc
    if not path.exists():
        raise WarehouseNotReady(f"No warehouse at {path}")
    return duckdb.connect(str(path), read_only=True)


def _query(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    try:
        with _connect() as con:
            return con.execute(sql, params or []).df()
    except duckdb.CatalogException as exc:
        raise WarehouseNotReady(str(exc)) from exc


def daily_health(start: date, end: date) -> pd.DataFrame:
    return _query(
        """
        select calendar_date::timestamp as date, * exclude (calendar_date)
        from marts.fct_daily_health
        where calendar_date between ? and ?
        order by calendar_date
        """,
        [start, end],
    )


def activities(start: date, end: date) -> pd.DataFrame:
    return _query(
        """
        select
            activity_id,
            activity_name as name,
            activity_type as type,
            started_at_local as start,
            activity_date::timestamp as date,
            distance_km,
            duration_min,
            avg_hr,
            max_hr,
            calories,
            elevation_gain_m,
            aerobic_effect,
            anaerobic_effect,
            training_load,
            pace_min_per_km,
            hr_zone_1_min,
            hr_zone_2_min,
            hr_zone_3_min,
            hr_zone_4_min,
            hr_zone_5_min
        from marts.fct_activities
        where activity_date between ? and ?
        order by started_at_local
        """,
        [start, end],
    )


def activity_years() -> list[int]:
    """Calendar years with at least one activity, oldest first."""
    df = _query("select distinct year(activity_date) as year from marts.fct_activities order by year")
    return [int(y) for y in df["year"]]


def daily_body(start: date, end: date) -> pd.DataFrame:
    return _query(
        """
        select calendar_date::timestamp as date, * exclude (calendar_date)
        from marts.fct_daily_body
        where calendar_date between ? and ?
        order by calendar_date
        """,
        [start, end],
    )


def race_results() -> pd.DataFrame:
    """Every (half) marathon on record, oldest first. Not limited to the selected range: progression needs history."""
    return _query(
        """
        select race_date::timestamp as date, * exclude (race_date)
        from marts.fct_race_results
        order by race_date, activity_id
        """
    )


def race_predictions() -> pd.DataFrame:
    """Garmin's predicted race times for every day on record, oldest first."""
    return _query(
        """
        select calendar_date::timestamp as date, * exclude (calendar_date)
        from marts.fct_race_predictions
        order by calendar_date
        """
    )


def heart_rate_zones() -> dict[str, Any]:
    """Zone floors for the default sport, or {} if Garmin has not reported any zones."""
    df = _query("select * from marts.rpt_heart_rate_zones order by sport = 'DEFAULT' desc, sport limit 1")
    if df.empty:
        return {}
    return {str(k): (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}


def current_status() -> dict[str, Any]:
    df = _query("select * from marts.rpt_current_status")
    if df.empty:
        return {}
    return {str(k): (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}


def last_loaded_at() -> datetime | None:
    """When the last successful Garmin ingest ran, as naive UTC."""
    df = _query("select observed_at_utc as loaded_at from marts.rpt_garmin_freshness where signal = 'last ingest'")
    value = df["loaded_at"].iloc[0]
    return None if pd.isna(value) else pd.Timestamp(value).to_pydatetime()


def freshness() -> pd.DataFrame:
    return _query("select * from marts.rpt_garmin_freshness")


def metric_coverage(start: date, end: date) -> pd.DataFrame:
    return _query(
        """
        select calendar_date, metric, is_present
        from marts.rpt_metric_coverage
        where calendar_date between ? and ?
        order by calendar_date, metric
        """,
        [start, end],
    )


def metric_lag() -> pd.DataFrame:
    return _query("select * from marts.rpt_metric_lag")
