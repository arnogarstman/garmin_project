"""Garmin Connect source: one raw record per API call, payload untouched.

Per-day endpoints are fetched for every day in [since, today]. Activities come
from one range query (garminconnect pages through it internally), and the
device snapshot is taken once per run as a freshness signal.
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

# Logical endpoint name -> garminconnect method taking a YYYY-MM-DD date.
DAY_ENDPOINTS: dict[str, str] = {
    "daily_summary": "get_user_summary",
    "sleep": "get_sleep_data",
    "hrv": "get_hrv_data",
    "training_readiness": "get_training_readiness",
    "training_status": "get_training_status",
}

DEFAULT_LOOKBACK_DAYS = 30
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 5.0
RETRYABLE = (GarminConnectConnectionError, GarminConnectTooManyRequestsError)


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

    def extract(self, since: date | None = None) -> Iterator[RawRecord]:
        end = self._today()
        start = since or end - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)
        if start > end:
            raise ValueError(f"since {start} is after today {end}")
        logger.info("Extracting Garmin data for %s to %s", start, end)

        api = self._connect()
        yield from self._call("device_last_used", api.get_device_last_used, {})
        yield from self._call(
            "activities",
            partial(api.get_activities_by_date, start.isoformat(), end.isoformat()),
            {"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
        day = start
        while day <= end:
            for endpoint, method in DAY_ENDPOINTS.items():
                fetch = partial(getattr(api, method), day.isoformat())
                yield from self._call(endpoint, fetch, {"date": day.isoformat()})
            day += timedelta(days=1)

    def _call(self, endpoint: str, fetch: Callable[[], Any], params: dict[str, Any]) -> Iterator[RawRecord]:
        """Yield the response as one record. Retries transient failures with
        exponential backoff; a 404 is logged and skipped so one missing day
        does not abort a backfill. Anything else fails the run, which leaves
        the warehouse untouched because loads are all-or-nothing."""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                payload = fetch()
            except GarminConnectNotFoundError:
                logger.warning("Garmin %s %s: not found, skipped", endpoint, params)
                return
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
                yield RawRecord(endpoint, payload, params)
                return
