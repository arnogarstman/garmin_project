from datetime import date
from pathlib import Path

import pandas as pd

from garminreader import goal as goals
from garminreader.dashboard import goal_coach as gc
from garminreader.dashboard import weekly

TODAY = date(2026, 3, 10)


def _goal(**overrides: object) -> goals.TrainingGoal:
    fields: dict[str, object] = {"goal": "Half marathon", "target": "under 1:45", "event_date": date(2026, 5, 5)}
    return goals.TrainingGoal.model_validate(fields | overrides)


def test_goal_survives_save_and_load(tmp_path: Path) -> None:
    """A saved goal is read back with every field intact.

    The goal is stored as JSON on disk so it survives dashboard restarts; dates and
    optional numbers must round-trip exactly.
    """
    path = tmp_path / "nested" / "goal.json"
    goal = _goal(weekly_hours=6.5, constraints="sore knee")
    goals.save_goal(goal, path)
    assert goals.load_goal(path) == goal


def test_no_goal_before_one_is_saved(tmp_path: Path) -> None:
    """Without a goal file, load_goal() returns None so the dashboard can ask for one."""
    assert goals.load_goal(tmp_path / "goal.json") is None


def test_unreadable_goal_file_is_ignored(tmp_path: Path) -> None:
    """A corrupt or outdated goal file is treated as no goal instead of crashing the dashboard.

    The user can then simply save a new goal over it.
    """
    path = tmp_path / "goal.json"
    path.write_text('{"target": "no goal field"}')
    assert goals.load_goal(path) is None


def test_weeks_to_event() -> None:
    """Whole weeks until the event; None without an event date or when the date has passed.

    8 weeks out is 2026-05-05 from 2026-03-10. A past event must not produce a negative
    horizon in the prompt.
    """
    assert _goal().weeks_to_event(TODAY) == 8
    assert _goal(event_date=None).weeks_to_event(TODAY) is None
    assert _goal(event_date=date(2026, 3, 1)).weeks_to_event(TODAY) is None


def test_describe_includes_only_what_was_filled_in() -> None:
    """The goal text for the prompt lists the filled-in fields and skips empty optional ones.

    Without an event date it states the default planning horizon instead, so Claude
    always knows how many weeks the phases must cover.
    """
    text = _goal().describe(TODAY)
    assert "Half marathon" in text and "under 1:45" in text and "8 weeks from today" in text
    assert "hours per week" not in text and "Constraints" not in text

    no_date = _goal(event_date=None).describe(TODAY)
    assert f"next {goals.DEFAULT_HORIZON_WEEKS} weeks" in no_date


def test_weekly_summary_groups_by_week_and_type() -> None:
    """Activities are summed per ISO week (Monday start) and activity type.

    Two runs in the week of 2026-03-02 collapse into one row with their total distance and
    the longest single session; the ride and the next week's run stay separate.
    """
    activities = pd.DataFrame(
        {
            "activity_id": [1, 2, 3, 4],
            "date": pd.to_datetime(["2026-03-02", "2026-03-04", "2026-03-04", "2026-03-09"]),
            "type": ["running", "running", "cycling", "running"],
            "distance_km": [5.0, 12.0, 30.0, 8.0],
            "duration_min": [30.0, 70.0, 60.0, 45.0],
            "training_load": [40.0, 110.0, 80.0, 60.0],
        }
    )
    summary = weekly.training_summary(activities)
    runs = summary[(summary["type"] == "running") & (summary["week_start"] == date(2026, 3, 2))].iloc[0]
    assert (runs["sessions"], runs["distance_km"], runs["longest_min"]) == (2, 17.0, 70.0)
    assert len(summary) == 3


def test_context_contains_goal_and_handles_missing_data() -> None:
    """The prompt always contains today's date and the goal, even when there is no Garmin data yet.

    Empty tables are rendered as "(no data)" rather than raising, so a new user can still
    get an assessment (which should then report the data gaps).
    """
    context = gc.build_context(_goal(), pd.DataFrame(), pd.DataFrame(), {}, TODAY)
    assert "Today is 2026-03-10." in context
    assert "Half marathon" in context
    assert "(no data)" in context


def test_context_includes_zones_races_predictions_and_body() -> None:
    """The optional data sources each get their own section in the prompt when provided.

    Race predictions are reduced to one row per week (the last of the week), since daily
    predictions barely change and would only add tokens.
    """
    predictions = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-03-02", "2026-03-03", "2026-03-09"]),
            "predicted_half_marathon_s": [6000, 5990, 5950],
        }
    )
    context = gc.build_context(
        _goal(),
        pd.DataFrame(),
        pd.DataFrame(),
        {},
        TODAY,
        hr_zones={"zone_2_floor_bpm": 116},
        race_results=pd.DataFrame({"race_distance": ["Half marathon"], "finish_time_s": [6100]}),
        race_predictions=predictions,
        body_df=pd.DataFrame({"date": ["2026-03-09"], "weight_kg": [83.2]}),
    )
    assert "'zone_2_floor_bpm': 116" in context
    assert "Half marathon,6100" in context
    assert "5990" in context and "6000" not in context
    assert "83.2" in context
