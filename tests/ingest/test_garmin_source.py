from datetime import date
from typing import Any

import pytest
from garminconnect import GarminConnectConnectionError, GarminConnectNotFoundError

from garminreader.ingest.sources.garmin.source import DAY_ENDPOINTS, MAX_ATTEMPTS, GarminSource

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
            return {"method": method, "args": list(args), "nested": {"keep": None}}

        return call


def _source(api: FakeGarmin, sleeps: list[float] | None = None) -> GarminSource:
    return GarminSource(
        connect=lambda: api,
        today=lambda: TODAY,
        sleep=(sleeps if sleeps is not None else []).append,
    )


def test_one_record_per_endpoint_and_day_with_payload_untouched() -> None:
    api = FakeGarmin()
    records = list(_source(api).extract(since=date(2026, 3, 9)))

    assert [r.endpoint for r in records[:2]] == ["device_last_used", "activities"]
    assert records[1].params == {"start_date": "2026-03-09", "end_date": "2026-03-10"}
    day_records = records[2:]
    assert len(day_records) == 2 * len(DAY_ENDPOINTS)
    assert {r.params["date"] for r in day_records} == {"2026-03-09", "2026-03-10"}
    sleep = next(r for r in day_records if r.endpoint == "sleep")
    assert sleep.payload == {"method": "get_sleep_data", "args": ["2026-03-09"], "nested": {"keep": None}}


def test_default_lookback_when_never_loaded() -> None:
    records = list(_source(FakeGarmin()).extract())
    assert records[1].params["start_date"] == "2026-02-09"


def test_retries_transient_errors_with_backoff() -> None:
    api = FakeGarmin({"get_hrv_data": [GarminConnectConnectionError("boom"), GarminConnectConnectionError("boom")]})
    sleeps: list[float] = []
    records = list(_source(api, sleeps).extract(since=TODAY))

    assert sum(r.endpoint == "hrv" for r in records) == 1
    assert sleeps == [5.0, 10.0]


def test_gives_up_after_max_attempts() -> None:
    api = FakeGarmin({"get_hrv_data": [GarminConnectConnectionError("down")] * MAX_ATTEMPTS})
    with pytest.raises(GarminConnectConnectionError):
        list(_source(api).extract(since=TODAY))


def test_not_found_is_skipped() -> None:
    api = FakeGarmin({"get_training_status": [GarminConnectNotFoundError("404")]})
    records = list(_source(api).extract(since=TODAY))
    assert "training_status" not in {r.endpoint for r in records}
    assert "sleep" in {r.endpoint for r in records}


def test_rejects_since_in_the_future() -> None:
    with pytest.raises(ValueError):
        list(_source(FakeGarmin()).extract(since=date(2026, 3, 11)))
