from datetime import date
from typing import Any, ClassVar

import pytest
from garminconnect import GarminConnectConnectionError, GarminConnectNotFoundError

from garminreader.ingest.sources.garmin.source import DAY_ENDPOINTS, MAX_ATTEMPTS, SNAPSHOT_ENDPOINTS, GarminSource

TODAY = date(2026, 3, 10)


class FakeGarmin:
    """Stands in for garminconnect.Garmin: records calls, returns canned payloads."""

    def __init__(self, failures: dict[str, list[Exception]] | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.failures = failures or {}

    def __getattr__(self, method: str) -> Any:
        def call(*args: Any) -> Any:
            self.calls.append((method, args))
            pending = self.failures.get(method)
            if pending:
                raise pending.pop(0)
            if method == "get_activities_by_date":
                return [{"activityId": 11, "activityName": "Run"}, {"activityId": 12, "activityName": "Ride"}]
            return {"method": method, "args": list(args), "nested": {"keep": None}}

        return call


def _source(api: FakeGarmin, sleeps: list[float] | None = None) -> GarminSource:
    return GarminSource(
        connect=lambda: api,
        today=lambda: TODAY,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_one_record_per_endpoint_and_day_with_payload_untouched() -> None:
    """A two-day extract yields the expected records, in order, with payloads untouched.

    Expected order: one record per snapshot endpoint (device, heart rate zones), then one
    record per activity from a single date-range query (keyed by activity_id), then one
    record per daily endpoint per day (2 days x len(DAY_ENDPOINTS), keyed by date). Each
    payload must be exactly what the API returned, including nested nulls.
    """
    api = FakeGarmin()
    records = list(_source(api).extract(since=date(2026, 3, 9)))

    n_snapshots = len(SNAPSHOT_ENDPOINTS)
    assert [r.endpoint for r in records[: n_snapshots + 2]] == [*SNAPSHOT_ENDPOINTS, "activity", "activity"]
    assert records[n_snapshots].params == {"activity_id": 11}
    assert records[n_snapshots].payload == {"activityId": 11, "activityName": "Run"}
    assert ("get_activities_by_date", ("2026-03-09", "2026-03-10")) in api.calls
    day_records = [r for r in records if "date" in r.params]
    assert len(day_records) == 2 * len(DAY_ENDPOINTS)
    assert {r.params["date"] for r in day_records} == {"2026-03-09", "2026-03-10"}
    sleep = next(r for r in day_records if r.endpoint == "sleep")
    assert sleep.payload == {"method": "get_sleep_data", "args": ["2026-03-09"], "nested": {"keep": None}}


def test_default_lookback_when_never_loaded() -> None:
    """Without `since`, the extract covers the last DEFAULT_LOOKBACK_DAYS (30) days, today included.

    With TODAY = 2026-03-10 the window starts on 2026-02-09, so the activities range query must
    be called with those two dates.
    """
    api = FakeGarmin()
    list(_source(api).extract())
    assert ("get_activities_by_date", ("2026-02-09", "2026-03-10")) in api.calls


def test_retries_transient_errors_with_backoff() -> None:
    """Transient connection errors are retried with exponential backoff until the call succeeds.

    get_hrv_data fails twice and works on the third attempt. The source waits 5s and then 10s
    (BACKOFF_SECONDS, doubling each retry) and still yields exactly one hrv record, so a flaky
    network does not abort the run. Sleeps are captured, not actually performed.
    """
    api = FakeGarmin({"get_hrv_data": [GarminConnectConnectionError("boom"), GarminConnectConnectionError("boom")]})
    sleeps: list[float] = []
    records = list(_source(api, sleeps).extract(since=TODAY))

    assert sum(r.endpoint == "hrv" for r in records) == 1
    assert sleeps == [5.0, 10.0]


def test_gives_up_after_max_attempts() -> None:
    """An endpoint that keeps failing raises after MAX_ATTEMPTS tries instead of retrying forever.

    The error propagates out of extract() and fails the run. Because loads are all-or-nothing,
    the warehouse is left untouched.
    """
    api = FakeGarmin({"get_hrv_data": [GarminConnectConnectionError("down")] * MAX_ATTEMPTS})
    with pytest.raises(GarminConnectConnectionError):
        list(_source(api).extract(since=TODAY))


def test_not_found_is_skipped() -> None:
    """A 404 on one endpoint is skipped and the rest of the extract continues.

    The skipped endpoint (training_status here) produces no record, but other endpoints such as
    sleep are still fetched. One missing day of data must not abort a backfill.
    """
    api = FakeGarmin({"get_training_status": [GarminConnectNotFoundError("404")]})
    records = list(_source(api).extract(since=TODAY))
    assert "training_status" not in {r.endpoint for r in records}
    assert "sleep" in {r.endpoint for r in records}


def test_rejects_since_in_the_future() -> None:
    """A `since` date after today raises ValueError instead of silently extracting nothing."""
    with pytest.raises(ValueError):
        list(_source(FakeGarmin()).extract(since=date(2026, 3, 11)))


def test_race_predictions_are_requested_per_day() -> None:
    """Race predictions are fetched one day at a time, so each record is keyed by its date.

    The range variant of the API would put the request window in every payload, which would
    make an unchanged prediction look changed whenever the window shifts.
    """
    api = FakeGarmin()
    list(_source(api).extract(since=TODAY))
    assert ("get_race_predictions", ("2026-03-10", "2026-03-10", "daily")) in api.calls


def test_until_limits_the_window() -> None:
    """With `until`, per-day endpoints stop at that day: a Dagster partition fetches only its own window."""
    api = FakeGarmin()
    records = list(_source(api).extract(since=date(2026, 3, 8), until=date(2026, 3, 9)))
    assert {r.params["date"] for r in records if "date" in r.params} == {"2026-03-08", "2026-03-09"}
    assert ("get_activities_by_date", ("2026-03-08", "2026-03-09")) in api.calls


class FakeGarminWithCoach(FakeGarmin):
    """A calendar with weigh-ins and the workouts of one adaptive Coach plan."""

    CALENDAR: ClassVar[dict[str, Any]] = {
        "calendarItems": [
            {"itemType": "weight", "trainingPlanId": None},
            {"itemType": "fbtAdaptiveWorkout", "trainingPlanId": 7, "title": "Basis"},
            {"itemType": "fbtAdaptiveWorkout", "trainingPlanId": 7, "title": "Sprint"},
        ]
    }

    def get_scheduled_workouts(self, year: int, month: int) -> dict[str, Any]:
        self.calls.append(("get_scheduled_workouts", (year, month)))
        return self.CALENDAR


def test_garmin_coach_plans_named_in_the_calendar_are_fetched() -> None:
    """The month's calendar is stored, and each adaptive Coach plan it schedules workouts for is
    fetched once; other calendar items (weigh-ins, activities) name no plan."""
    api = FakeGarminWithCoach()
    records = list(_source(api).extract(since=TODAY))
    coach = [r for r in records if r.endpoint in ("calendar", "adaptive_training_plan")]
    assert [(r.endpoint, r.params) for r in coach] == [
        ("calendar", {"year": 2026, "month": 3}),
        ("adaptive_training_plan", {"plan_id": 7}),
    ]
    assert coach[0].payload == FakeGarminWithCoach.CALENDAR
    assert ("get_adaptive_training_plan_by_id", (7,)) in api.calls


def test_no_coach_plan_means_no_plan_call() -> None:
    api = FakeGarmin()
    list(_source(api).extract(since=TODAY))
    assert not [c for c in api.calls if c[0] == "get_adaptive_training_plan_by_id"]
