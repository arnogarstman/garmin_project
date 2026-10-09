"""Garmin Connect source: one raw record per API call, payload untouched.

Per-day endpoints are fetched for every day in [since, today]. Activities come
from one range query (garminconnect pages through it internally) and are
stored one record per activity, keyed by activity_id, so an activity seen
again in a later window is recognised as unchanged. Snapshot endpoints (the
device, as a freshness signal, and the heart rate zones) are taken once per
run; the loader only stores them when they change, which builds their history.
"""

import logging
import time
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from functools import partial
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from garminreader.ingest.sources.base import RawRecord
from garminreader.ingest.sources.garmin import auth

logger = logging.getLogger(__name__)

# Logical endpoint name -> call for one YYYY-MM-DD date.
DAY_ENDPOINTS: dict[str, Callable[[Garmin, str], Any]] = {
    "daily_summary": lambda api, day: api.get_user_summary(day),
    "sleep": lambda api, day: api.get_sleep_data(day),
    "hrv": lambda api, day: api.get_hrv_data(day),
    "training_readiness": lambda api, day: api.get_training_readiness(day),
    "training_status": lambda api, day: api.get_training_status(day),
    "weigh_ins": lambda api, day: api.get_daily_weigh_ins(day),
    "race_predictions": lambda api, day: api.get_race_predictions(day, day, "daily"),
}

# Logical endpoint name -> garminconnect method without arguments, called once per run.
SNAPSHOT_ENDPOINTS: dict[str, str] = {
    "device_last_used": "get_device_last_used",
    "heart_rate_zones": "get_heart_rate_zones",
}

DEFAULT_LOOKBACK_DAYS = 30
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 5.0
RETRYABLE = (GarminConnectConnectionError, GarminConnectTooManyRequestsError)
_NOT_FOUND = object()


class GarminSource:
    name = "garmin"

    def __init__(
        self,
        connect: Callable[[], Garmin] = auth.connect,
        today: Callable[[], date] = date.today,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._connect = connect
        self._today = today
        self._sleep = sleep

    def extract(self, since: date | None = None, until: date | None = None) -> Iterator[RawRecord]:
        end = min(until, self._today()) if until else self._today()
        start = since or end - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)
        if start > end:
            raise ValueError(f"since {start} is after today {end}")
        logger.info("Extracting Garmin data for %s to %s", start, end)

        api = self._connect()
        for endpoint, method in SNAPSHOT_ENDPOINTS.items():
            yield from self._call(endpoint, getattr(api, method), {})
        activities = self._fetch(
            "activities",
            partial(api.get_activities_by_date, start.isoformat(), end.isoformat()),
            {"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
        for activity in activities if isinstance(activities, list) else []:
            yield RawRecord("activity", activity, {"activity_id": activity["activityId"]})
        day = start
        while day <= end:
            for endpoint, call in DAY_ENDPOINTS.items():
                fetch = partial(call, api, day.isoformat())
                yield from self._call(endpoint, fetch, {"date": day.isoformat()})
            day += timedelta(days=1)

    def _call(self, endpoint: str, fetch: Callable[[], Any], params: dict[str, Any]) -> Iterator[RawRecord]:
        """Yield the response as one record (nothing if it was a 404)."""
        payload = self._fetch(endpoint, fetch, params)
        if payload is not _NOT_FOUND:
            yield RawRecord(endpoint, payload, params)

    def _fetch(self, endpoint: str, fetch: Callable[[], Any], params: dict[str, Any]) -> Any:
        """Return the response. Retries transient failures with exponential
        backoff; a 404 is logged and returned as _NOT_FOUND so one missing day
        does not abort a backfill. Anything else fails the run, which leaves
        the warehouse untouched because loads are all-or-nothing."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                payload = fetch()
            except GarminConnectNotFoundError:
                logger.warning("Garmin %s %s: not found, skipped", endpoint, params)
                return _NOT_FOUND
            except RETRYABLE as exc:
                if attempt == MAX_ATTEMPTS:
                    raise
                delay = BACKOFF_SECONDS * 2 ** (attempt - 1)
                logger.warning(
                    "Garmin %s %s failed (%s); retry %d/%d in %.0fs",
                    endpoint,
                    params,
                    exc,
                    attempt,
                    MAX_ATTEMPTS - 1,
                    delay,
                )
                self._sleep(delay)
            else:
                return payload
        raise AssertionError("unreachable")
