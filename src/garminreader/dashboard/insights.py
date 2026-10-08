"""Turns raw daily/activity DataFrames into plain-language insights: what a
metric means, what changed, and what that change typically implies."""

from dataclasses import dataclass
from typing import Any

import pandas as pd

RECENT_WINDOW_DAYS = 7


@dataclass
class Insight:
    title: str
    explanation: str
    finding: str
    direction: str  # "up" | "down" | "flat" | "na"


def _split_recent_baseline(df: pd.DataFrame, col: str) -> tuple[pd.Series, pd.Series]:
    series = df.dropna(subset=[col]).sort_values("date")
    if len(series) < 4:
        return series[col], series[col].iloc[0:0]
    recent = series.tail(RECENT_WINDOW_DAYS)
    baseline = series.iloc[: -len(recent)] if len(series) > len(recent) else series
    return recent[col], baseline[col]


def _pct_change(recent_mean: float, baseline_mean: float) -> float:
    if baseline_mean == 0:
        return 0.0
    return (recent_mean - baseline_mean) / abs(baseline_mean) * 100


def _direction(delta_pct: float, threshold: float = 3.0) -> str:
    if delta_pct > threshold:
        return "up"
    if delta_pct < -threshold:
        return "down"
    return "flat"


def resting_hr_insight(df: pd.DataFrame) -> Insight | None:
    recent, baseline = _split_recent_baseline(df, "resting_hr")
    if recent.empty or baseline.empty:
        return None
    r_mean, b_mean = recent.mean(), baseline.mean()
    delta = r_mean - b_mean
    direction = _direction(_pct_change(r_mean, b_mean), threshold=1.5)
    if direction == "down":
        finding = (
            f"Your resting heart rate averaged {r_mean:.0f} bpm over the last "
            f"{len(recent)} days, about {abs(delta):.1f} bpm lower than your "
            f"{b_mean:.0f} bpm baseline. A falling resting heart rate usually "
            "reflects improving cardiovascular fitness or better recovery."
        )
    elif direction == "up":
        finding = (
            f"Your resting heart rate averaged {r_mean:.0f} bpm recently, "
            f"about {abs(delta):.1f} bpm higher than your {b_mean:.0f} bpm "
            "baseline. A rising resting heart rate can signal accumulated "
            "fatigue, stress, illness, or overtraining."
        )
    else:
        finding = (
            f"Your resting heart rate has stayed steady around {r_mean:.0f} bpm, in line with your recent baseline."
        )
    return Insight(
        title="Resting Heart Rate",
        explanation=(
            "Resting heart rate (RHR) is one of the most reliable day-to-day "
            "signals of cardiovascular fitness and recovery state."
        ),
        finding=finding,
        direction=direction,
    )


def sleep_insight(df: pd.DataFrame) -> Insight | None:
    recent, baseline = _split_recent_baseline(df, "sleep_score")
    if recent.empty:
        return None
    r_mean = recent.mean()
    b_mean = baseline.mean() if not baseline.empty else r_mean
    direction = _direction(_pct_change(r_mean, b_mean), threshold=5.0)
    quality = "excellent" if r_mean >= 80 else "good" if r_mean >= 70 else "fair" if r_mean >= 60 else "poor"
    finding = f"Your average sleep score over the last {len(recent)} nights is {r_mean:.0f} ({quality})" + (
        f", compared to {b_mean:.0f} before that." if not baseline.empty else "."
    )
    return Insight(
        title="Sleep Quality",
        explanation=(
            "Garmin's sleep score blends duration, time in each sleep stage, "
            "restlessness, and how well your sleep matches your body's needs. "
            "It's a strong predictor of next-day recovery and readiness."
        ),
        finding=finding,
        direction=direction,
    )


def hrv_insight(df: pd.DataFrame) -> Insight | None:
    recent, baseline = _split_recent_baseline(df, "hrv_last_night_avg")
    if recent.empty or baseline.empty:
        return None
    r_mean, b_mean = recent.mean(), baseline.mean()
    direction = _direction(_pct_change(r_mean, b_mean), threshold=4.0)
    latest_status = df.dropna(subset=["hrv_status"]).sort_values("date")
    status_txt = (
        f" Garmin currently classifies your HRV status as {latest_status['hrv_status'].iloc[-1]}."
        if not latest_status.empty
        else ""
    )
    if direction == "down":
        finding = (
            f"Your HRV averaged {r_mean:.0f} ms recently versus a {b_mean:.0f} ms "
            f"baseline: a downward shift, which often coincides with fatigue "
            f"or incomplete recovery.{status_txt}"
        )
    elif direction == "up":
        finding = (
            f"Your HRV averaged {r_mean:.0f} ms recently versus a {b_mean:.0f} ms "
            f"baseline: trending up, which usually reflects good adaptation "
            f"and recovery.{status_txt}"
        )
    else:
        finding = f"Your HRV has been stable around {r_mean:.0f} ms.{status_txt}"
    return Insight(
        title="Heart Rate Variability",
        explanation=(
            "HRV reflects how well your autonomic nervous system is balancing "
            "stress and recovery. Falling HRV relative to your own baseline is "
            "one of the earliest warning signs of overreaching."
        ),
        finding=finding,
        direction=direction,
    )


def stress_insight(df: pd.DataFrame) -> Insight | None:
    recent, baseline = _split_recent_baseline(df, "avg_stress")
    if recent.empty:
        return None
    r_mean = recent.mean()
    b_mean = baseline.mean() if not baseline.empty else r_mean
    direction = _direction(_pct_change(r_mean, b_mean), threshold=5.0)
    # for stress, "up" in value is bad, so invert for display wording only
    finding = f"Average all-day stress over the last {len(recent)} days is {r_mean:.0f}/100" + (
        f", versus {b_mean:.0f}/100 before." if not baseline.empty else "."
    )
    return Insight(
        title="Stress Load",
        explanation=(
            "Garmin derives an all-day stress score from heart rate variability "
            "patterns. Sustained high stress (above ~50) alongside hard training "
            "reduces the recovery benefit of sleep."
        ),
        finding=finding,
        direction=direction,
    )


def body_battery_insight(df: pd.DataFrame) -> Insight | None:
    recent, baseline = _split_recent_baseline(df, "body_battery_highest")
    if recent.empty:
        return None
    r_mean = recent.mean()
    b_mean = baseline.mean() if not baseline.empty else r_mean
    direction = _direction(_pct_change(r_mean, b_mean), threshold=5.0)
    finding = (
        f"Your Body Battery peaked at an average of {r_mean:.0f}/100 each day "
        f"over the last {len(recent)} days" + (f", versus {b_mean:.0f}/100 before." if not baseline.empty else ".")
    )
    return Insight(
        title="Body Battery",
        explanation=(
            "Body Battery estimates your energy reserves from sleep, stress, "
            "and activity. A daily peak that's consistently low suggests you're "
            "starting most days already short on recovery."
        ),
        finding=finding,
        direction=direction,
    )


def training_volume_insight(activities_df: pd.DataFrame) -> Insight | None:
    if activities_df.empty:
        return None
    df = activities_df.dropna(subset=["date"]).copy()
    df["week"] = df["date"].dt.to_period("W")
    weekly = df.groupby("week")["duration_min"].sum().sort_index()
    if len(weekly) < 2:
        return None
    recent_week = weekly.iloc[-1]
    prior_weeks = weekly.iloc[:-1]
    prior_avg = prior_weeks.mean()
    direction = _direction(_pct_change(recent_week, prior_avg), threshold=10.0)
    finding = (
        f"This week you trained {recent_week:.0f} minutes across "
        f"{df[df['week'] == weekly.index[-1]].shape[0]} sessions, versus a "
        f"{prior_avg:.0f} minute weekly average before that."
    )
    return Insight(
        title="Training Volume",
        explanation=(
            "Comparing this week's training time to your recent average shows "
            "whether your load is ramping up, holding steady, or tapering off."
        ),
        finding=finding,
        direction=direction,
    )


def vo2max_insight(current_status: dict[str, Any]) -> Insight | None:
    vo2 = current_status.get("vo2max")
    if not vo2:
        return None
    return Insight(
        title="VO2 Max",
        explanation=(
            "VO2 max estimates the maximum amount of oxygen your body can use "
            "during exercise, the single best proxy for aerobic fitness. It "
            "moves slowly, over weeks to months of consistent training."
        ),
        finding=f"Garmin currently estimates your VO2 max at {vo2:.1f}.",
        direction="na",
    )


def build_all_insights(
    daily_df: pd.DataFrame, activities_df: pd.DataFrame, current_status: dict[str, Any]
) -> list[Insight]:
    candidates = [
        resting_hr_insight(daily_df),
        sleep_insight(daily_df),
        hrv_insight(daily_df),
        stress_insight(daily_df),
        body_battery_insight(daily_df),
        training_volume_insight(activities_df),
        vo2max_insight(current_status),
    ]
    return [c for c in candidates if c is not None]
