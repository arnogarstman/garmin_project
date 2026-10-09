import json
import re
from pathlib import Path
from typing import Any

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


def test_live_page_embeds_the_query_and_no_data() -> None:
    sql = data.live_sql(days=30)
    html = render.render_live("garmin", sql, {"goal": None, "profile": "prod"})
    assert _script_value(html, "__SNAPSHOT__") is None
    assert _script_value(html, "__LIVE__") == {
        "server": render.LIVE_SERVER,
        "tool": render.LIVE_TOOL,
        "database": "garmin",
        "sql": sql,
        "goal": None,
        "profile": "prod",
    }


def _same_timestamps(value: object) -> object:
    """DuckDB's JSON writes timestamps with a space, the snapshot as ISO 8601 with a T."""
    if isinstance(value, str):
        return re.sub(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:)", r"\1 \2", value)
    if isinstance(value, list):
        return [_same_timestamps(v) for v in value]
    if isinstance(value, dict):
        return {k: _same_timestamps(v) for k, v in value.items()}
    return value


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


def test_live_sql_returns_the_snapshot_payload(tmp_path: Path) -> None:
    """The live statement yields what the snapshot queries do, as JSON, rows in the same order."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute("create schema marts")
    for name, sql in MARTS.items():
        con.execute(f"create table marts.{name} as {sql}")

    snapshot: dict[str, Any] = {key: data._rows(con, sql.format(days=30)) for key, sql in data.QUERIES.items()}
    for key in data.SINGLE_ROW:
        snapshot[key] = snapshot[key][0] if snapshot[key] else None
    row = con.execute(data.live_sql(days=30)).fetchone()
    assert row is not None
    live = json.loads(row[0])

    assert set(live) == {*data.QUERIES, "built_at"}
    for key in data.QUERIES:
        assert _same_timestamps(live[key]) == _same_timestamps(snapshot[key]), key
    assert [r["activity_name"] for r in live["recent"]] == [f"Run {i}" for i in range(8)]
