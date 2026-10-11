from pathlib import Path
from typing import Any

import pytest

from garminreader.ingest.sources.base import RawRecord
from garminreader.ingest.sources.garmin import workout_check
from garminreader.ingest.storage import RawStore


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
    RawStore(warehouse).load("garmin", [RawRecord("activity", {"activityId": 1}, {"activity_id": 1})])
    garmin = FakeGarmin([{"activityId": 2}, {"activityId": 1}])
    assert workout_check.check(lambda: garmin) is True
    RawStore(warehouse).load("garmin", [RawRecord("activity", {"activityId": 2}, {"activity_id": 2})])
    assert workout_check.check(lambda: garmin) is False


def test_only_garmin_activity_records_count(warehouse: str) -> None:
    """A review of the activity (the coach source) is not the activity itself."""
    RawStore(warehouse).load("coach", [RawRecord("workout_review", {}, {"activity_id": 2})])
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 2}])) is True


def test_an_empty_warehouse_or_account(warehouse: str) -> None:
    assert workout_check.check(lambda: FakeGarmin([{"activityId": 5}])) is True
    assert workout_check.check(lambda: FakeGarmin([])) is False


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
