"""Fetches data from Garmin Connect and shapes it into pandas DataFrames.

Caching is split by how settled the data is. Today and yesterday keep
changing as the watch syncs (steps, stress, last night's sleep and HRV), so
they use a short TTL. Older days are final and stay cached for a week.

Failed requests raise out of the cached functions, so Streamlit never caches
an error as "no data". Callers pass a `FetchErrors` to collect failures and
show them in the UI.

Cached functions take `_api` (leading underscore so Streamlit's cache does
not try to hash the client object) plus `display_name` as an explicit cache
key so cached data never leaks across accounts.
"""

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st
from garminconnect import Garmin

logger = logging.getLogger(__name__)

LIVE_DAYS = 2  # today and yesterday
LIVE_TTL = 10 * 60
SETTLED_TTL = 7 * 24 * 3600

# Garmin's raw API returns trainingStatus as a numeric code rather than the
# label shown in the Connect app.
TRAINING_STATUS_BY_CODE = {
    0: "NO_STATUS",
    1: "DETRAINING",
    2: "RECOVERY",
    3: "MAINTAINING",
    4: "PRODUCTIVE",
    5: "PEAKING",
    6: "OVERREACHING",
    7: "OVERTRAINING",
}

# Garmin client method for each per-day endpoint.
DAY_ENDPOINTS: dict[str, str] = {
    "summary": "get_stats",
    "sleep": "get_sleep_data",
    "hrv": "get_hrv_data",
    "readiness": "get_training_readiness",
    "training_status": "get_training_status",
}


@dataclass
class FetchErrors:
    """Requests that failed during one page load."""

    failures: list[str] = field(default_factory=list)

    def record(self, what: str, exc: Exception) -> None:
        logger.warning("Garmin request failed for %s: %s", what, exc)
        self.failures.append(what)


def daterange(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def is_live(day: date) -> bool:
    """Whether a day's data can still change on Garmin's side."""
    return (date.today() - day).days < LIVE_DAYS


# ---------------------------------------------------------------------------
# Per-day fetchers (cached per day so widening a date range only fetches the
# new days, not ones already loaded).
# ---------------------------------------------------------------------------


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def _fetch_live_day(_api: Garmin, display_name: str, endpoint: str, date_str: str) -> Any:
    return getattr(_api, DAY_ENDPOINTS[endpoint])(date_str)


@st.cache_data(ttl=SETTLED_TTL, show_spinner=False)
def _fetch_settled_day(
    _api: Garmin, display_name: str, endpoint: str, date_str: str
) -> Any:
    return getattr(_api, DAY_ENDPOINTS[endpoint])(date_str)


def _fetch_day(
    api: Garmin, display_name: str, endpoint: str, day: date, errors: FetchErrors
) -> Any:
    fetch = _fetch_live_day if is_live(day) else _fetch_settled_day
    try:
        return fetch(api, display_name, endpoint, day.isoformat())
    except Exception as exc:  # garminconnect raises HTTP, auth and parsing errors alike
        errors.record(f"{endpoint} {day.isoformat()}", exc)
        return None


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def _fetch_activities(
    _api: Garmin, display_name: str, start_str: str, end_str: str
) -> list[dict[str, Any]]:
    return _api.get_activities_by_date(start_str, end_str) or []


def clear_recent_cache() -> None:
    """Drop cached data that can still change (today, yesterday and activity
    lists). Settled days stay cached, so a refresh costs a handful of calls."""
    _fetch_live_day.clear()
    _fetch_activities.clear()


def _first(x: Any) -> dict[str, Any]:
    """Garmin returns some endpoints as a list of entries per day; take the
    most relevant (first) one, or the dict itself if it isn't a list."""
    if isinstance(x, list):
        return x[0] if x else {}
    return x or {}


def build_daily_dataframe(
    api: Garmin,
    display_name: str,
    start: date,
    end: date,
    errors: FetchErrors,
    progress: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """One row per day with wellness/recovery metrics."""
    rows = []
    days = list(daterange(start, end))
    for i, d in enumerate(days):
        summary = _fetch_day(api, display_name, "summary", d, errors) or {}
        sleep = _fetch_day(api, display_name, "sleep", d, errors) or {}
        hrv = _fetch_day(api, display_name, "hrv", d, errors) or {}
        readiness = _first(_fetch_day(api, display_name, "readiness", d, errors))

        sleep_dto = sleep.get("dailySleepDTO") or {}
        sleep_scores = sleep_dto.get("sleepScores") or {}
        overall_sleep_score = (sleep_scores.get("overall") or {}).get("value")
        hrv_summary = hrv.get("hrvSummary") or {}

        rows.append(
            {
                "date": d,
                "resting_hr": summary.get("restingHeartRate"),
                "steps": summary.get("totalSteps"),
                "calories": summary.get("totalKilocalories"),
                "avg_stress": summary.get("averageStressLevel"),
                "body_battery_charged": summary.get("bodyBatteryChargedValue"),
                "body_battery_drained": summary.get("bodyBatteryDrainedValue"),
                "body_battery_highest": summary.get("bodyBatteryHighestValue"),
                "body_battery_lowest": summary.get("bodyBatteryLowestValue"),
                "sleep_seconds": summary.get("sleepingSeconds")
                or sleep_dto.get("sleepTimeSeconds"),
                "deep_sleep_seconds": sleep_dto.get("deepSleepSeconds"),
                "light_sleep_seconds": sleep_dto.get("lightSleepSeconds"),
                "rem_sleep_seconds": sleep_dto.get("remSleepSeconds"),
                "awake_seconds": sleep_dto.get("awakeSleepSeconds"),
                "sleep_score": overall_sleep_score,
                "hrv_last_night_avg": hrv_summary.get("lastNightAvg"),
                "hrv_weekly_avg": hrv_summary.get("weeklyAvg"),
                "hrv_status": hrv_summary.get("status"),
                "readiness_score": readiness.get("score"),
                "readiness_level": readiness.get("level"),
            }
        )
        if progress is not None:
            progress((i + 1) / len(days))

    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_activities(
    api: Garmin, display_name: str, start: date, end: date, errors: FetchErrors
) -> pd.DataFrame:
    try:
        activities = _fetch_activities(api, display_name, start.isoformat(), end.isoformat())
    except Exception as exc:  # garminconnect raises HTTP, auth and parsing errors alike
        errors.record("activities", exc)
        activities = []

    rows = []
    for a in activities:
        activity_type = (a.get("activityType") or {}).get("typeKey", "unknown")
        distance_m = a.get("distance") or 0
        duration_s = a.get("duration") or 0
        rows.append(
            {
                "activity_id": a.get("activityId"),
                "name": a.get("activityName"),
                "type": activity_type,
                "start": a.get("startTimeLocal"),
                "distance_km": distance_m / 1000 if distance_m else 0,
                "duration_min": duration_s / 60 if duration_s else 0,
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "calories": a.get("calories"),
                "elevation_gain_m": a.get("elevationGain"),
                "aerobic_effect": a.get("aerobicTrainingEffect"),
                "anaerobic_effect": a.get("anaerobicTrainingEffect"),
                "training_load": a.get("activityTrainingLoad"),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["start"] = pd.to_datetime(df["start"])
        df["date"] = df["start"].dt.normalize()
        df["pace_min_per_km"] = df.apply(
            lambda r: (r["duration_min"] / r["distance_km"])
            if r["distance_km"] and r["distance_km"] > 0.1
            else None,
            axis=1,
        )
    return df


def get_current_status(
    api: Garmin, display_name: str, as_of: date, errors: FetchErrors
) -> dict[str, Any]:
    """Latest-snapshot metrics that don't need a historical trend: VO2max,
    training status label, and acute:chronic workload ratio. Reuses the
    per-day cache, so the summary and readiness already loaded for the daily
    table cost no extra calls."""
    result: dict[str, Any] = {}

    status = _fetch_day(api, display_name, "training_status", as_of, errors) or {}

    latest_status_by_device = (
        (status.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")
        or {}
    )
    if latest_status_by_device:
        first_device = next(iter(latest_status_by_device.values()), {})
        status_code = first_device.get("trainingStatus")
        result["training_status"] = TRAINING_STATUS_BY_CODE.get(status_code, status_code)
        result["training_status_feedback"] = first_device.get(
            "trainingStatusFeedbackPhrase"
        )

    vo2max_block = status.get("mostRecentVO2Max") or {}
    generic_vo2 = (vo2max_block.get("generic") or {}) if vo2max_block else {}
    result["vo2max"] = generic_vo2.get("vo2MaxPreciseValue") or generic_vo2.get(
        "vo2MaxValue"
    )

    load_block = status.get("mostRecentTrainingLoadBalance") or {}
    metrics_by_device = (
        load_block.get("metricsTrainingLoadBalanceDTOMap") or {}
    )
    if metrics_by_device:
        first_load = next(iter(metrics_by_device.values()), {})
        result["acwr"] = first_load.get("dailyAcuteChronicWorkloadRatio") or first_load.get(
            "dailyTrainingLoadAcuteChronicRatio"
        )
        result["acwr_status"] = first_load.get("acwrStatus") or first_load.get(
            "trainingBalanceFeedbackPhrase"
        )

    readiness = _first(_fetch_day(api, display_name, "readiness", as_of, errors))
    result["readiness_score"] = readiness.get("score")
    result["readiness_level"] = readiness.get("level")
    result["readiness_feedback"] = readiness.get("feedbackLong") or readiness.get(
        "feedbackShort"
    )

    summary = _fetch_day(api, display_name, "summary", as_of, errors) or {}
    result["body_battery_current"] = summary.get(
        "bodyBatteryMostRecentValue"
    ) or summary.get("bodyBatteryHighestValue")
    result["resting_hr"] = summary.get("restingHeartRate")

    return result
