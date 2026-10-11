from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from garminreader import claude
from garminreader.ingest.sources.base import RawRecord
from garminreader.ingest.sources.coach import source
from garminreader.ingest.sources.coach.review import PROMPT_VERSION, WorkoutReview
from garminreader.ingest.storage import RawStore

TODAY = date(2026, 10, 11)

REVIEW = WorkoutReview(
    status="good",
    headline="Easy and controlled",
    session_type="easy run",
    summary="Ran easy.",
    went_well=["Heart rate stayed low"],
    watch_out=[],
    recovery="A day is enough.",
    next_session="Intervals on Tuesday.",
)


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """A local warehouse with one activity a day for the 10 days up to TODAY (ids 0 to 9, 0 the newest)."""
    path = str(tmp_path / "w.duckdb")
    monkeypatch.setenv("DATABASE", path)
    monkeypatch.setenv("DATA_PROFILE", "prod")
    monkeypatch.setenv("GOAL_PATH", str(tmp_path / "goal.json"))
    with duckdb.connect(path) as con:
        con.execute("create schema marts")
        con.execute(f"""
            create table marts.fct_activities as
            select i::bigint as activity_id, 'Run ' || i as activity_name, 'running' as activity_type,
                   (date '{TODAY}' - i::int)::timestamp + interval 7 hour as started_at_local,
                   date '{TODAY}' - i::int as activity_date, 8.0 as distance_km, 45.0 as duration_min,
                   5.6 as pace_min_per_km, 140.0 as avg_hr, 160.0 as max_hr, 3.0 as aerobic_effect,
                   0.5 as anaerobic_effect, 80.0 as training_load, 5.0 as hr_zone_1_min, 30.0 as hr_zone_2_min,
                   10.0 as hr_zone_3_min, 0.0 as hr_zone_4_min, 0.0 as hr_zone_5_min, false as is_tagged_race
            from range(10) t(i)""")
        con.execute(f"""
            create table marts.fct_daily_health as
            select date '{TODAY}' - i::int as calendar_date, 50 as resting_hr, 60 as hrv_last_night_avg,
                   'balanced' as hrv_status, 80 as sleep_score, 27000 as sleep_seconds, 70 as readiness_score,
                   90 as body_battery_highest, 25 as avg_stress, 300.0 as acute_load, 280.0 as chronic_load,
                   1.07 as acwr, 'productive' as training_status, 50.0 as vo2max
            from range(20) t(i)""")
        con.execute(f"""
            create table marts.fct_race_predictions as
            select date '{TODAY}' as calendar_date, 1300 as predicted_5k_s, 2700 as predicted_10k_s,
                   6000 as predicted_half_marathon_s, 12600 as predicted_marathon_s""")
        con.execute("create table marts.rpt_heart_rate_zones as select 'running' as sport, 120 as zone_1_floor_bpm")
    RawStore(path).last_loaded_at("coach")  # creates the raw tables
    return path


class FakeClaude:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, fail: set[int] | None = None) -> None:
        self.prompts: list[str] = []
        self.fail = fail or set()
        monkeypatch.setattr(claude, "available", lambda: True)
        monkeypatch.setattr(claude, "parse", self.parse)

    def parse(self, system: str, content: str, output_format: type[WorkoutReview]) -> WorkoutReview:
        self.prompts.append(content)
        if any(f"\n{i},Run {i}," in content.split("## Activities")[0] for i in self.fail):
            raise RuntimeError("Claude declined to answer.")
        return REVIEW


def test_reviews_recent_unreviewed_workouts_newest_first(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only workouts in the lookback window without a review are reviewed, the newest first.

    Each record carries the activity, model and prompt version in its params and Claude's answer
    untouched as its payload, so dbt can model it like any raw response.
    """
    FakeClaude(monkeypatch)
    RawStore(warehouse).load(
        "coach", [RawRecord(source.ENDPOINT, params={"activity_id": 1, "model": "m", "prompt_version": 1}, payload={})]
    )
    records = list(source.CoachSource().extract(until=TODAY))
    ids = [r.params["activity_id"] for r in records]
    assert ids == [0, 2, 3, 4, 5]  # 1 is reviewed; capped at MAX_PER_RUN
    assert all(r.endpoint == source.ENDPOINT for r in records)
    assert records[0].params == {"activity_id": 0, "model": claude.MODEL, "prompt_version": PROMPT_VERSION}
    assert records[0].payload == REVIEW.model_dump(mode="json")


def test_lookback_limits_how_far_back_reviews_go(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """An older `since` (the ingest CLI's resume point) cannot shrink the window below the lookback,
    and nothing older than `since` is reviewed when it reaches further back."""
    FakeClaude(monkeypatch)
    monkeypatch.setattr(source, "MAX_PER_RUN", 100)
    recent = [r.params["activity_id"] for r in source.CoachSource().extract(since=TODAY, until=TODAY)]
    assert recent == list(range(source.LOOKBACK_DAYS + 1))
    backfill = [
        r.params["activity_id"] for r in source.CoachSource().extract(since=TODAY - timedelta(days=8), until=TODAY)
    ]
    assert backfill == list(range(9))


def test_prompt_holds_only_what_came_before_the_workout(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeClaude(monkeypatch)
    monkeypatch.setattr(source, "MAX_PER_RUN", 2)
    list(source.CoachSource().extract(until=TODAY))
    prompt = fake.prompts[1]  # activity 1, yesterday
    history = prompt.split("## Activities")[1].split("## Daily")[0]
    assert "Run 2," in history and "Run 1," not in history and "Run 0," not in history
    assert str(TODAY) not in prompt.split("## Daily")[1].split("## Garmin")[0]
    assert "(no goal set)" in prompt


def test_without_api_key_nothing_is_reviewed(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(claude, "available", lambda: False)
    monkeypatch.setattr(claude, "parse", lambda *a, **k: pytest.fail("Claude called without a key"))
    assert list(source.CoachSource().extract(until=TODAY)) == []


def test_a_failed_review_skips_only_that_workout(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """One failed answer leaves the others stored; the next run retries the failed one."""
    FakeClaude(monkeypatch, fail={2})
    ids = [r.params["activity_id"] for r in source.CoachSource().extract(until=TODAY)]
    assert ids == [0, 1, 3, 4]


def test_all_reviews_failing_fails_the_run(warehouse: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """When nothing succeeds (a bad key, an outage) the step fails visibly instead of storing nothing."""
    FakeClaude(monkeypatch, fail=set(range(10)))
    with pytest.raises(RuntimeError, match="Every workout review failed"):
        list(source.CoachSource().extract(until=TODAY))
