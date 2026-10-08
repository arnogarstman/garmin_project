"""Read-only access to the dbt marts. The dashboard's only database access.

Columns are aliased to the names the dashboard modules use.
"""

from datetime import date, datetime
from typing import Any

import duckdb
import pandas as pd

from garminreader import config


class WarehouseNotReady(RuntimeError):
    """The warehouse file or the marts do not exist yet."""


def _connect() -> duckdb.DuckDBPyConnection:
    path = config.duckdb_path()
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
            pace_min_per_km
        from marts.fct_activities
        where activity_date between ? and ?
        order by started_at_local
        """,
        [start, end],
    )


def current_status() -> dict[str, Any]:
    df = _query("select * from marts.rpt_current_status")
    if df.empty:
        return {}
    return {str(k): (None if pd.isna(v) else v) for k, v in df.iloc[0].to_dict().items()}


def last_loaded_at() -> datetime | None:
    """When the last successful Garmin ingest ran, as naive UTC."""
    df = _query("select max(loaded_at) at time zone 'UTC' as loaded_at from raw._loads where source = 'garmin'")
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
