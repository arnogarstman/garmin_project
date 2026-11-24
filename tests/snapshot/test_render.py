import datetime as dt
import json
from pathlib import Path

import duckdb

from garminreader.snapshot import data, render


def _script_value(html: str, name: str) -> object:
    start = html.index(f"window.{name}=") + len(f"window.{name}=")
    return json.JSONDecoder().raw_decode(html, start)[0]


def test_payload_cannot_close_the_script_element() -> None:
    """Text from the warehouse (an activity name) must not end the inline <script> early."""
    html = render.render({"history": [{"name": "</script><b>x</b>"}]})
    assert "</script><b>" not in html
    payload = _script_value(html, "__SNAPSHOT__")
    assert isinstance(payload, dict)
    assert payload["history"][0]["name"] == "</script><b>x</b>"


def test_template_markers_are_all_filled() -> None:
    html = render.render({})
    assert render.DATA_MARKER not in html
    assert render.LIVE_MARKER not in html
    assert render.APP_MARKER not in html
    assert "<title>" in html
    assert _script_value(html, "__LIVE__") is None


def test_live_page_embeds_the_queries_and_no_data() -> None:
    queries = data.live_queries(days=30)
    html = render.render_live("garmin", queries, data.SINGLE_ROW, {"goal": None, "profile": "prod"})
    assert _script_value(html, "__SNAPSHOT__") is None
    assert _script_value(html, "__LIVE__") == {
        "server": render.LIVE_SERVER,
        "tool": render.LIVE_TOOL,
        "database": "garmin",
        "queries": queries,
        "single_row": sorted(data.SINGLE_ROW),
        "goal": None,
        "profile": "prod",
    }


MARTS = {
    "fct_daily_health": """
        select current_date - i::int as calendar_date, 50 + i as resting_hr, 40 as hrv_last_night_avg,
               80 as sleep_score, 45.0 as vo2max, 1.0 as acwr, 30.0 as acute_load, 30.0 as chronic_load,
               70 as readiness_score
        from range(3) t(i)""",
    "fct_activities": """
        select (current_date - i::int)::timestamp + interval (i) hour as started_at_local,
               current_date - i::int as activity_date, 'Run ' || i as activity_name, 'running' as activity_type,
               5.0 + i as distance_km, 30.0 as duration_min, 6.0 as pace_min_per_km, 150.0 as avg_hr,
               50.0 as training_load, 1.0 as hr_zone_1_min, 2.0 as hr_zone_2_min, 3.0 as hr_zone_3_min,
               4.0 as hr_zone_4_min, 5.0 as hr_zone_5_min, 20.0 as elevation_gain_m
        from range(10) t(i)""",
    "fct_daily_body": """
        select current_date - i::int as calendar_date, 80.0 - i / 10 as weight_kg
        from range(5) t(i)""",
    "fct_race_predictions": """
        select current_date - i::int as calendar_date, 1500 as predicted_5k_s, 3100 as predicted_10k_s,
               6800 as predicted_half_marathon_s, 14400 as predicted_marathon_s
        from range(15) t(i)""",
    "fct_race_results": """
        select current_date - 1 as race_date, 'Race' as activity_name, 'half_marathon' as race_distance,
               6700.0 as finish_time_s, 5.3 as pace_min_per_km, 170.0 as avg_hr, true as is_personal_best""",
    "rpt_metric_lag": """
        select m as metric, current_date as latest_date, 0 as days_behind, 100.0 as completeness_pct
        from (values ('sleep'), ('hrv')) t(m)""",
    "rpt_current_status": "select 'productive' as training_status, 45.0 as vo2max",
    "fct_daily_energy": """
        select current_date - i::int as calendar_date, 2500.0 + i as total_kcal, (i % 2)::bigint as workouts,
               600.0 as workout_kcal, 8.0 as run_km, 80.0 - i / 10 as weight_kg
        from range(50) t(i)""",
    "fct_coach_workouts": """
        select current_date + i::int as calendar_date, 'Basis' as workout_name, '5:30/km' as description,
               30.0 as duration_min, 'AEROBIC_BASE' as training_effect, 'NOT_COMPLETE' as status, false as is_long,
               false as is_rest_day, 'Halve Marathon plan' as plan_name, date '2027-01-10' as plan_end_date
        from range(-3, 4) t(i)""",
    "fct_sleep_effects": """
        select current_date - i::int as calendar_date, 7.0 + i / 10 as sleep_hours, 80 as sleep_score,
               7.2 as sleep_hours_7d, 0.2 as deep_share, 0.25 as rem_share, 23.5 as bedtime_hour,
               50 as hrv, 48 as resting_hr, 70 as readiness_score, (i % 2)::bigint as runs,
               8.0 as run_km, 5.5 as run_pace_min_per_km, 150.0 as run_avg_hr, 0.01 as run_efficiency_vs_base,
               80.0 as weight_kg, -0.1 as weight_change_kg
        from range(40) t(i)""",
    "fct_training_blocks": """
        select date_trunc('week', current_date - 7 * i::int)::date as week_start, 20.0 as run_km_per_week,
               3.0 as runs_per_week, 12.0 as longest_run_km, 300.0 as load_per_week, 0.6 as easy_share,
               0.3 as tempo_share, 0.1 as hard_share, 6600 as hm_before_s, 6500 as hm_after_s,
               -0.015 as hm_change, 0.5 as vo2max_change
        from range(10) t(i)""",
    "fct_aerobic_fitness": """
        select date_trunc('week', current_date - 7 * i::int)::date as week_start, 12::bigint as runs,
               1.2 as efficiency, 5.5 as ref_pace_min_per_km, 148.0 - i as hr_at_ref_pace
        from range(10) t(i)""",
    "fct_energy_balance": """
        select current_date - 1 - i::int as calendar_date, 2800.0 as burn_kcal, 80.0 as weight_kg,
               10::bigint as weigh_ins, -0.2 as weight_kg_per_week, -220.0 as balance_kcal,
               2580.0 as implied_intake_kcal
        from range(60) t(i)""",
    "fct_run_efficiency": """
        select current_date - i::int as activity_date, (current_date - i::int)::timestamp + interval 19 hour
                   as started_at_local, 19.0 as start_hour, 'evening' as time_of_day, 8.0 as distance_km,
               5.5 as pace_min_per_km, 150.0 as avg_hr, 60.0 as training_load, 0.02 as efficiency_vs_base,
               7.2 as next_sleep_hours, 80 as next_sleep_score, 55 as next_hrv, 3.5 as hours_to_bedtime
        from range(10) t(i)""",
    "fct_workout_reviews": """
        select current_date - i::int as activity_date, (current_date - i::int)::timestamp as started_at_local,
               'Run ' || i as activity_name, 'running' as activity_type, 'good' as status, 'Fine' as headline,
               'easy run' as session_type, 'Ran easy.' as summary, ['Low heart rate', 'Even pace'] as went_well,
               []::varchar[] as watch_out, 'A day.' as recovery, 'Intervals.' as next_session,
               now()::timestamp as reviewed_at_utc
        from range(8) t(i)""",
}


def test_live_queries_return_the_snapshot_payload(tmp_path: Path) -> None:
    """Each live query, run on its own as the page does, yields that part of the snapshot payload."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    for name, sql in MARTS.items():
        con.execute(f"create table marts.{name} as {sql}")

    queries = data.live_queries(days=30)
    assert set(queries) == set(data.QUERIES)
    for key, sql in queries.items():
        assert data._rows(con, sql) == data._rows(con, data.QUERIES[key].format(days=30)), key
    for key in data.SINGLE_ROW:
        assert len(data._rows(con, queries[key])) <= 1, key
    assert [r["name"] for r in data._rows(con, queries["history"])] == [f"Run {i}" for i in reversed(range(10))]
    assert [r["activity_name"] for r in data._rows(con, queries["runs"])] == [f"Run {i}" for i in reversed(range(10))]


def test_reviews_reach_the_page_newest_first_with_their_lists(tmp_path: Path) -> None:
    """The lists travel as JSON text, which the page parses the same way from either mode."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    con.execute(f"create table marts.fct_workout_reviews as {MARTS['fct_workout_reviews']}")
    rows = data._rows(con, data.live_queries()["reviews"])
    assert [r["activity_name"] for r in rows] == [f"Run {i}" for i in range(6)]
    assert json.loads(rows[0]["went_well"]) == ["Low heart rate", "Even pace"]
    assert json.loads(rows[0]["watch_out"]) == []


def test_energy_covers_six_weeks_oldest_first(tmp_path: Path) -> None:
    """The meal plan's budget reads six weeks of burn and weigh-ins, in date order."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    con.execute(f"create table marts.fct_daily_energy as {MARTS['fct_daily_energy']}")
    rows = data._rows(con, data.live_queries()["energy"])
    assert len(rows) == 42
    assert [r["d"] for r in rows] == sorted(r["d"] for r in rows)
    assert {"kcal", "workouts", "workout_kcal", "run_km", "weight"} <= set(rows[0])


def test_sleep_covers_the_period_oldest_first(tmp_path: Path) -> None:
    """The Sleep tab reads one row per night in date order, within the period."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    con.execute(f"create table marts.fct_sleep_effects as {MARTS['fct_sleep_effects']}")
    rows = data._rows(con, data.live_queries(days=30)["sleep"])
    assert len(rows) == 30
    assert [r["d"] for r in rows] == sorted(r["d"] for r in rows)
    assert {"h", "score", "h7", "ef", "hrv", "rhr", "ready", "weight", "dw", "bed"} <= set(rows[0])


def test_balance_is_weekly_with_the_latest_day(tmp_path: Path) -> None:
    """The energy balance travels as one row per week (Sundays) plus the latest complete day."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    con.execute(f"create table marts.fct_energy_balance as {MARTS['fct_energy_balance']}")
    rows = data._rows(con, data.live_queries(days=365)["balance"])
    days = [dt.date.fromisoformat(r["d"]) for r in rows]
    assert days == sorted(days)
    assert days[-1] == dt.date.today() - dt.timedelta(days=1)
    assert all(d.isoweekday() == 7 for d in days[:-1])
    assert 8 <= len(rows) <= 10
