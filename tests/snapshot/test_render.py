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
