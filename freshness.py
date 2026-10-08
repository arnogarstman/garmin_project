"""Freshness and completeness checks for Garmin Connect data.

Sync signals come straight from the API rather than through the Streamlit
cache, so their timestamps say when Garmin last received data, not when the
app last fetched it. Garmin's payloads are undocumented, so every field is
read defensively and a missing field shows up as a gap instead of an error.
"""

import logging
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd
from garminconnect import Garmin

import garmin_data as gd

logger = logging.getLogger(__name__)

# Daily metric column per Garmin endpoint, used to judge whether a day's
# payload actually contained data.
COVERAGE_COLUMNS: dict[str, str] = {
    "summary": "resting_hr",
    "steps": "steps",
    "stress": "avg_stress",
    "body_battery": "body_battery_highest",
    "sleep": "sleep_score",
    "hrv": "hrv_last_night_avg",
    "readiness": "readiness_score",
}


def parse_timestamp(value: Any) -> pd.Timestamp | None:
    """Garmin mixes epoch milliseconds and ISO strings (GMT, no offset).
    Returns a UTC timestamp, or None when the value is missing or unparseable."""
    if value in (None, "", 0):
        return None
    try:
        if isinstance(value, int | float):
            return pd.Timestamp(value, unit="ms", tz="UTC")
        ts = pd.Timestamp(value)
    except (ValueError, TypeError):
        return None
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def _signal(
    name: str, fetch: Callable[[], Any], extract: Callable[[Any], Any]
) -> dict[str, Any]:
    try:
        payload = fetch()
        raw = extract(payload or {})
        error = None
    except Exception as exc:  # garminconnect raises HTTP, auth and parsing errors alike
        logger.warning("Freshness signal %s failed: %s", name, exc)
        raw, error = None, str(exc)
    return {"signal": name, "raw_value": raw, "timestamp_utc": parse_timestamp(raw), "error": error}


def sync_signals(api: Garmin, today: date | None = None) -> pd.DataFrame:
    """One row per freshness signal with its UTC timestamp and age in hours."""
    day = (today or date.today()).isoformat()
    rows = [
        _signal(
            "device last upload",
            api.get_device_last_used,
            lambda p: p.get("lastUsedDeviceUploadTime"),
        ),
        _signal(
            "daily summary last sync",
            lambda: api.get_user_summary(day),
            lambda p: p.get("lastSyncTimestampGMT"),
        ),
        _signal(
            "last night's sleep end",
            lambda: api.get_sleep_data(day),
            lambda p: (p.get("dailySleepDTO") or {}).get("sleepEndTimestampGMT"),
        ),
        _signal(
            "latest activity start",
            api.get_last_activity,
            lambda p: p.get("startTimeGMT"),
        ),
    ]
    df = pd.DataFrame(rows)
    now = pd.Timestamp.now(tz="UTC")
    df["age_hours"] = (now - df["timestamp_utc"]).dt.total_seconds() / 3600
    return df


def coverage(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Boolean grid: one row per date, one column per metric, True if present."""
    grid = pd.DataFrame(
        {name: daily_df[col].notna() for name, col in COVERAGE_COLUMNS.items()}
    )
    grid.index = daily_df["date"].dt.date
    return grid


def metric_lag(daily_df: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Latest date with data per metric, how many days behind today it is,
    and how complete the metric is over the loaded range."""
    today = today or date.today()
    grid = coverage(daily_df)
    rows = []
    for metric in grid.columns:
        present = grid.index[grid[metric]]
        latest = max(present) if len(present) else None
        rows.append(
            {
                "metric": metric,
                "latest_date": latest,
                "days_behind": (today - latest).days if latest else None,
                "completeness_pct": round(grid[metric].mean() * 100, 1),
            }
        )
    return pd.DataFrame(rows)


def cache_policy(start: date, end: date) -> pd.DataFrame:
    """How the Streamlit app caches each day in the range."""
    return pd.DataFrame(
        {
            "date": day,
            "tier": "live" if gd.is_live(day) else "settled",
            "ttl_minutes": (gd.LIVE_TTL if gd.is_live(day) else gd.SETTLED_TTL) // 60,
        }
        for day in gd.daterange(start, end)
    )
