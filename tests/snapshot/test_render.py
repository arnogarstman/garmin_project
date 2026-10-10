import json
from pathlib import Path

import duckdb

from garminreader.snapshot import data, render


def _script_value(html: str, name: str) -> object:
    start = html.index(f"window.{name}=") + len(f"window.{name}=")
    return json.JSONDecoder().raw_decode(html, start)[0]


def test_payload_cannot_close_the_script_element() -> None:
    """Text from the warehouse (an activity name) must not end the inline <script> early."""
    html = render.render({"recent": [{"activity_name": "</script><b>x</b>"}]})
    assert "</script><b>" not in html
    payload = _script_value(html, "__SNAPSHOT__")
    assert isinstance(payload, dict)
    assert payload["recent"][0]["activity_name"] == "</script><b>x</b>"


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
               4.0 as hr_zone_4_min, 5.0 as hr_zone_5_min
        from range(10) t(i)""",
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
    assert [r["activity_name"] for r in data._rows(con, queries["recent"])] == [f"Run {i}" for i in range(8)]
    assert [r["activity_name"] for r in data._rows(con, queries["runs"])] == [f"Run {i}" for i in reversed(range(10))]
