"""Reads the marts into the JSON-ready payload the snapshot page renders.

Reads marts only. Aggregation for display (weekly sums, weekly samples of
predictions) happens here; modelling stays in dbt. The same queries feed the
live page, which runs each one through a connector.
"""

import datetime as dt
import decimal
from typing import Any

import duckdb

from garminreader import db
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
    "history": """
        select activity_date, hour(started_at_local) as hr, activity_name as name, activity_type as type,
               round(distance_km, 1) as km, round(duration_min) as min, round(pace_min_per_km, 2) as pace,
               round(avg_hr) as avg_hr, round(training_load) as load, round(elevation_gain_m) as elev
        from marts.fct_activities
        where activity_date > current_date - interval {days} day
        order by started_at_local
    """,
    "body": """
        select calendar_date as d, round(weight_kg, 1) as weight
        from marts.fct_daily_body
        where calendar_date > current_date - interval {days} day
        order by 1
    """,
    "runs": """
        select activity_date, activity_name, round(distance_km, 1) as km, round(duration_min, 1) as min,
               round(pace_min_per_km, 2) as pace, round(avg_hr) as avg_hr, round(hr_zone_1_min, 1) as z1,
               round(hr_zone_2_min, 1) as z2, round(hr_zone_3_min, 1) as z3, round(hr_zone_4_min, 1) as z4,
               round(hr_zone_5_min, 1) as z5
        from marts.fct_activities
        where activity_date > current_date - interval {days} day and activity_type ilike '%run%'
        order by started_at_local
    """,
    "reviews": """
        select activity_date, activity_name, activity_type, status, headline, session_type, summary,
               to_json(went_well) as went_well, to_json(watch_out) as watch_out, recovery, next_session,
               reviewed_at_utc
        from marts.fct_workout_reviews
        order by started_at_local desc
        limit 6
    """,
    "energy": """
        select calendar_date as d, total_kcal as kcal, workouts, round(workout_kcal) as workout_kcal,
               round(run_km, 1) as run_km, round(weight_kg, 2) as weight
        from marts.fct_daily_energy
        where calendar_date > current_date - interval 42 day
        order by 1
    """,
    "coach": """
        select calendar_date as d, workout_name as name, description, round(duration_min) as min,
               training_effect as effect, status, is_long, is_rest_day as rest, plan_name, plan_end_date
        from marts.fct_coach_workouts
        where calendar_date > current_date - interval 56 day
        order by calendar_date, workout_name
    """,
    "sleep": """
        select calendar_date as d, round(sleep_hours, 2) as h, sleep_score as score, round(sleep_hours_7d, 2) as h7,
               round(deep_share, 3) as deep, round(rem_share, 3) as rem, round(bedtime_hour, 2) as bed,
               hrv, resting_hr as rhr, readiness_score as ready, runs, round(run_km, 1) as km,
               round(run_pace_min_per_km, 2) as pace, round(run_avg_hr) as hr, round(run_efficiency_vs_base, 4) as ef,
               round(weight_kg, 2) as weight, round(weight_change_kg, 2) as dw
        from marts.fct_sleep_effects
        where calendar_date > current_date - interval {days} day
        order by 1
    """,
    "blocks": """
        select week_start as wk, round(run_km_per_week, 1) as km, round(runs_per_week, 2) as rpw,
               round(longest_run_km, 1) as lr, round(load_per_week) as load, round(easy_share, 3) as easy,
               round(tempo_share, 3) as tempo, round(hard_share, 3) as hard, hm_before_s as hm0,
               hm_after_s as hm1, round(hm_change, 4) as dhm, round(vo2max_change, 1) as dvo2
        from marts.fct_training_blocks
        where week_start > current_date - interval {days} day
        order by 1
    """,
    "aerobic": """
        select week_start as wk, runs, round(efficiency, 4) as ef, ref_pace_min_per_km as ref,
               round(hr_at_ref_pace, 1) as hr_ref
        from marts.fct_aerobic_fitness
        where week_start > current_date - interval {days} day
        order by 1
    """,
    "balance": """
        select calendar_date as d, round(burn_kcal) as burn, round(weight_kg, 2) as weight, weigh_ins,
               round(weight_kg_per_week, 3) as kg_wk, round(balance_kcal) as bal, round(implied_intake_kcal) as intake
        from marts.fct_energy_balance
        where calendar_date > current_date - interval {days} day
          and (dayofweek(calendar_date) = 0
               or calendar_date = (select max(calendar_date) from marts.fct_energy_balance))
        order by 1
    """,
    "lag": "select * from marts.rpt_metric_lag order by metric",
    "status": "select * from marts.rpt_current_status",
}

# Single-row queries: the payload holds the row itself, or null.
SINGLE_ROW = frozenset({"status", "zones"})


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


def load(days: int = 365) -> dict[str, Any]:
    """The page payload: the last `days` days of the marts plus the current status and goal."""
    with db.connect(read_only=True) as con:
        data: dict[str, Any] = {key: _rows(con, sql.format(days=int(days))) for key, sql in QUERIES.items()}
    for key in SINGLE_ROW:
        data[key] = data[key][0] if data[key] else None
    data.update(context())
    data["built_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    return data


def context() -> dict[str, Any]:
    """What the page shows besides the marts: the training goal from the goal file."""
    goal = load_goal()
    return {"goal": goal.model_dump(mode="json") if goal else None}


def live_queries(days: int = 365) -> dict[str, str]:
    """The payload's queries as the live page runs them, one connector call each: a
    connector caps the size of one result, so the marts do not travel as one value."""
    return {key: sql.format(days=int(days)).strip() for key, sql in QUERIES.items()}
