"""Fetches data from Garmin Connect and shapes it into pandas DataFrames.

All fetch functions take `_api` (leading underscore so Streamlit's cache
does not try to hash the client object) plus `display_name` as an explicit
cache key so cached data never leaks across accounts.
"""

from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

DAY_CACHE_TTL = 6 * 3600  # a day's data rarely changes once the day is over
RANGE_CACHE_TTL = 15 * 60


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------------------
# Per-day fetchers (cached individually so widening a date range only fetches
# the new days, not ones already loaded).
# ---------------------------------------------------------------------------


@st.cache_data(ttl=DAY_CACHE_TTL, show_spinner=False)
def _fetch_day_summary(_api, display_name: str, date_str: str) -> dict:
    try:
        return _api.get_stats(date_str) or {}
    except Exception:
        return {}


@st.cache_data(ttl=DAY_CACHE_TTL, show_spinner=False)
def _fetch_day_sleep(_api, display_name: str, date_str: str) -> dict:
    try:
        return _api.get_sleep_data(date_str) or {}
    except Exception:
        return {}


@st.cache_data(ttl=DAY_CACHE_TTL, show_spinner=False)
def _fetch_day_hrv(_api, display_name: str, date_str: str) -> dict:
    try:
        return _api.get_hrv_data(date_str) or {}
    except Exception:
        return {}


@st.cache_data(ttl=DAY_CACHE_TTL, show_spinner=False)
def _fetch_day_readiness(_api, display_name: str, date_str: str):
    try:
        return _api.get_training_readiness(date_str) or []
    except Exception:
        return []


def _first(x):
    """Garmin returns some endpoints as a list of entries per day; take the
    most relevant (first) one, or the dict itself if it isn't a list."""
    if isinstance(x, list):
        return x[0] if x else {}
    return x or {}


def build_daily_dataframe(
    api, display_name: str, start: date, end: date, progress=None
) -> pd.DataFrame:
    """One row per day with wellness/recovery metrics."""
    rows = []
    days = list(daterange(start, end))
    for i, d in enumerate(days):
        date_str = d.isoformat()
        summary = _fetch_day_summary(api, display_name, date_str)
        sleep = _fetch_day_sleep(api, display_name, date_str)
        hrv = _fetch_day_hrv(api, display_name, date_str)
        readiness = _first(_fetch_day_readiness(api, display_name, date_str))

        sleep_dto = (sleep or {}).get("dailySleepDTO") or {}
        sleep_scores = sleep_dto.get("sleepScores") or {}
        overall_sleep_score = (sleep_scores.get("overall") or {}).get("value")
        hrv_summary = (hrv or {}).get("hrvSummary") or {}

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


@st.cache_data(ttl=RANGE_CACHE_TTL, show_spinner=False)
def get_activities(_api, display_name: str, start: date, end: date) -> pd.DataFrame:
    try:
        activities = _api.get_activities_by_date(start.isoformat(), end.isoformat())
    except Exception:
        activities = []

    rows = []
    for a in activities or []:
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


@st.cache_data(ttl=RANGE_CACHE_TTL, show_spinner=False)
def get_current_status(_api, display_name: str, as_of: date) -> dict:
    """Latest-snapshot metrics that don't need a historical trend: VO2max,
    training status label, and acute:chronic workload ratio."""
    date_str = as_of.isoformat()
    result: dict = {}

    try:
        status = _api.get_training_status(date_str) or {}
    except Exception:
        status = {}

    latest_status_by_device = (
        (status.get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData")
        or {}
    )
    if latest_status_by_device:
        first_device = next(iter(latest_status_by_device.values()), {})
        result["training_status"] = first_device.get("trainingStatus")
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

    try:
        readiness = _first(_api.get_training_readiness(date_str))
    except Exception:
        readiness = {}
    result["readiness_score"] = readiness.get("score")
    result["readiness_level"] = readiness.get("level")
    result["readiness_feedback"] = readiness.get("feedbackLong") or readiness.get(
        "feedbackShort"
    )

    try:
        summary = _api.get_stats(date_str) or {}
    except Exception:
        summary = {}
    result["body_battery_current"] = summary.get(
        "bodyBatteryMostRecentValue"
    ) or summary.get("bodyBatteryHighestValue")
    result["resting_hr"] = summary.get("restingHeartRate")

    return result
