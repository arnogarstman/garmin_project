from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from garminreader.ingest.sources.base import RawRecord
from garminreader.ingest.sources.garmin import workout_check
from garminreader.ingest.storage import RawStore

# A time inside the training hours, on a day without stored activities unless a test adds one.
NOON = datetime(2026, 10, 12, 12, 0, tzinfo=workout_check.TIMEZONE)


def at(t: datetime) -> Any:
    return lambda: t


def activity(activity_id: int, day: str = "2026-10-11") -> RawRecord:
    return RawRecord(
        "activity", {"activityId": activity_id, "startTimeLocal": f"{day} 07:00:00"}, {"activity_id": activity_id}
    )


class FakeGarmin:
    def __init__(self, activities: list[dict[str, Any]]) -> None:
        self.activities = activities

    def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        return self.activities[start : start + limit]


@pytest.fixture
def warehouse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "w.duckdb")
    monkeypatch.setenv("DATABASE", path)
    monkeypatch.setenv("DATA_PROFILE", "prod")
    return path


def test_a_workout_not_in_raw_is_new(warehouse: str) -> None:
    """Garmin's newest activity counts as new until a load has stored it."""
    RawStore(warehouse).load("garmin", [activity(1)])
    garmin = FakeGarmin([{"activityId": 2}, {"activityId": 1}])
    assert workout_check.check(lambda: garmin, at(NOON)) is True
    RawStore(warehouse).load("garmin", [activity(2)])
    assert workout_check.check(lambda: garmin, at(NOON)) is False


def test_only_garmin_activity_records_count(warehouse: str) -> None:
    """A review of the activity (the coach source) is not the activity itself."""
    RawStore(warehouse).load("coach", [RawRecord("workout_review", {}, {"activity_id": 2})])
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 2}]), at(NOON)) is True


def test_an_empty_warehouse_or_account(warehouse: str) -> None:
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 5}]), at(NOON)) is True
    assert workout_check.check(lambda: FakeGarmin([]), at(NOON)) is False


def no_garmin() -> Any:
    pytest.fail("Garmin was called")


@pytest.mark.parametrize("hour", [0, 5, 22, 23])
def test_outside_training_hours_garmin_is_not_asked(warehouse: str, hour: int) -> None:
    assert workout_check.check(no_garmin, at(NOON.replace(hour=hour))) is False


@pytest.mark.parametrize("hour", [6, 21])
def test_the_training_hours_include_both_ends(warehouse: str, hour: int) -> None:
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 9}]), at(NOON.replace(hour=hour))) is True


def test_once_todays_workout_is_stored_garmin_is_not_asked(warehouse: str) -> None:
    """Most days have one workout; a second one waits for the next morning's daily refresh."""
    RawStore(warehouse).load("garmin", [activity(1, day="2026-10-11")])  # yesterday's
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 2}]), at(NOON)) is True
    RawStore(warehouse).load("garmin", [activity(2, day="2026-10-12")])  # today's
    assert workout_check.check(no_garmin, at(NOON)) is False


def test_a_failed_check_says_not_new_and_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A broken session must not fail every frequent check; the daily refresh reports it."""

    def broken() -> bool:
        raise RuntimeError("No working Garmin session")

    monkeypatch.setattr(workout_check, "check", broken)
    workout_check.main()
    out = capsys.readouterr()
    assert out.out == "new=false\n"
    assert "::warning::Workout check failed: No working Garmin session" in out.err
