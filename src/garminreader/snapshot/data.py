"""Reads the marts into the JSON-ready payload the snapshot page renders.

Reads marts only, like the dashboard. Aggregation for display (weekly sums,
weekly samples of predictions) happens here; modelling stays in dbt.
"""

import datetime as dt
import decimal
from pathlib import Path
from typing import Any

import duckdb

from garminreader import config
from garminreader.goal import load_goal

Row = dict[str, Any]

QUERIES: dict[str, str] = {
    "daily": """
        select calendar_date as d, resting_hr as rhr, hrv_last_night_avg as hrv, sleep_score as sleep,
               vo2max, round(acwr, 2) as acwr, round(acute_load) as acute, round(chronic_load) as chronic,
               readiness_score as ready
        from marts.fct_daily_health
        where calendar_date > current_date - interval {days} day
        order by 1
    """,
    "weekly": """
        select date_trunc('week', activity_date)::date as wk,
               round(sum(case when activity_type ilike '%run%' then distance_km else 0 end), 1) as run_km,
               count(*) as n, round(sum(duration_min) / 60, 1) as hrs, round(sum(training_load)) as tload
        from marts.fct_activities
        where activity_date > current_date - interval {days} day
        group by 1 order by 1
    """,
    "pred": """
        select calendar_date as d, predicted_5k_s as p5, predicted_10k_s as p10,
               predicted_half_marathon_s as phm, predicted_marathon_s as pm
        from marts.fct_race_predictions
        where calendar_date > current_date - interval {days} day and dayofweek(calendar_date) = 1
        order by 1
    """,
    "races": """
        select race_date, activity_name, race_distance, finish_time_s, pace_min_per_km, avg_hr, is_personal_best
        from marts.fct_race_results
        where race_date > current_date - interval {days} day
        order by race_date
    """,
    "types": """
        select activity_type, count(*) as n, round(sum(distance_km)) as km, round(sum(duration_min) / 60, 1) as h
        from marts.fct_activities
        where activity_date > current_date - interval {days} day
        group by 1 order by 2 desc
    """,
    "zones": """
        select round(sum(hr_zone_1_min)) as z1, round(sum(hr_zone_2_min)) as z2, round(sum(hr_zone_3_min)) as z3,
               round(sum(hr_zone_4_min)) as z4, round(sum(hr_zone_5_min)) as z5
        from marts.fct_activities
        where activity_date > current_date - interval {days} day
    """,
    "recent": """
        select activity_date, activity_name, activity_type, round(distance_km, 2) as km,
               round(duration_min, 1) as min, round(pace_min_per_km, 2) as pace, avg_hr
        from marts.fct_activities
        order by started_at_local desc
        limit 8
    """,
    "lag": "select * from marts.rpt_metric_lag order by metric",
    "status": "select * from marts.rpt_current_status",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dt.date | dt.datetime):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[Row]:
    result = con.execute(sql)
    columns = [c[0] for c in result.description]
    return [dict(zip(columns, map(_jsonable, row), strict=True)) for row in result.fetchall()]


def load(warehouse: Path, days: int = 365) -> dict[str, Any]:
    """The page payload: the last `days` days of the marts plus the current status and goal."""
    with duckdb.connect(str(warehouse), read_only=True) as con:
        data: dict[str, Any] = {key: _rows(con, sql.format(days=int(days))) for key, sql in QUERIES.items()}
    data["status"] = data["status"][0] if data["status"] else None
    data["zones"] = data["zones"][0] if data["zones"] else None
    goal = load_goal()
    data["goal"] = goal.model_dump(mode="json") if goal else None
    data["profile"] = config.data_profile()
    data["built_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    return data
