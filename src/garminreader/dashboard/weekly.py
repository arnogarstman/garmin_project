"""Weekly roll-ups that make trends explicit in AI prompts."""

import pandas as pd


def week_start(dates: pd.Series) -> pd.Series:
    """Monday of each date's week, as a date."""
    mondays: pd.Series = dates.dt.to_period("W").apply(lambda p: p.start_time.date())
    return mondays


def training_summary(activities_df: pd.DataFrame) -> pd.DataFrame:
    """Volume per week and activity type."""
    if activities_df.empty:
        return activities_df
    df = activities_df.dropna(subset=["date"]).copy()
    df["week_start"] = week_start(df["date"])
    return (
        df.groupby(["week_start", "type"], as_index=False)
        .agg(
            sessions=("activity_id", "count"),
            distance_km=("distance_km", "sum"),
            duration_min=("duration_min", "sum"),
            longest_min=("duration_min", "max"),
            training_load=("training_load", "sum"),
        )
        .round(1)
        .sort_values(["week_start", "type"])
    )


def last_per_week(df: pd.DataFrame) -> pd.DataFrame:
    """The last row of each week, for daily series that barely change day to day."""
    if df.empty:
        return df
    weekly = df.copy()
    weekly["week_start"] = week_start(weekly["date"])
    return weekly.groupby("week_start", as_index=False).last().drop(columns=["date"])
