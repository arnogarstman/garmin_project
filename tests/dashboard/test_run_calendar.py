from datetime import date

import pandas as pd
import plotly.graph_objects as go
import pytest

from garminreader.dashboard import run_calendar as rc

ZONES = ["hr_zone_1_min", "hr_zone_2_min", "hr_zone_3_min", "hr_zone_4_min", "hr_zone_5_min"]


def _activities(rows: list[tuple[str, str, float, list[float]]]) -> pd.DataFrame:
    """(day, type, km, minutes in zones 1-5) per activity."""
    return pd.DataFrame(
        [
            {"activity_id": i, "date": pd.Timestamp(day), "type": kind, "distance_km": km, "duration_min": sum(zones)}
            | dict(zip(ZONES, zones, strict=True))
            for i, (day, kind, km, zones) in enumerate(rows)
        ]
    )


EASY = [10.0, 30.0, 5.0, 0.0, 0.0]  # 11% in zone 3+
HARD = [0.0, 10.0, 25.0, 10.0, 0.0]  # 78% in zone 3+

ACTIVITIES = _activities(
    [
        ("2026-10-05", "running", 5.0, EASY),
        ("2026-10-05", "trail_running", 3.25, HARD),
        ("2026-10-07", "cycling", 40.0, HARD),
        ("2026-10-07", "treadmill_running", 10.0, HARD),
    ]
)


def _month(fig: go.Figure, month: int) -> list[go.Scatter]:
    """The four traces of one month panel: day numbers, run circles, recovery dots, week totals."""
    return list(fig.data[4 * (month - 1) : 4 * month])


def test_running_days_sums_runs_and_ignores_other_sports() -> None:
    """Every running variant counts, several runs on one day add up, and a bike ride is not a run."""
    days = {r["day"]: r for r in rc.running_days(ACTIVITIES).to_dict("records")}
    assert (days[date(2026, 10, 5)]["km"], days[date(2026, 10, 5)]["runs"]) == (8.25, 2)
    assert days[date(2026, 10, 7)]["km"] == 10.0  # the 40 km ride is left out


def test_a_day_is_hard_when_half_its_heart_rate_time_is_in_zone_3_or_higher() -> None:
    """Intensity is judged on the whole day's heart rate time: an easy run plus a short hard one stays easy.

    On 5 October an easy 45 minutes (5 in zone 3+) and a hard 45 minutes (35 in zone 3+) give
    40 of 90 minutes, under half: easy. A day without heart rate data is neither.
    """
    days = {r["day"]: r for r in rc.running_days(ACTIVITIES).to_dict("records")}
    assert days[date(2026, 10, 5)]["hard_share"] == pytest.approx(40 / 90)
    assert not days[date(2026, 10, 5)]["is_hard"]
    assert days[date(2026, 10, 7)]["is_hard"]
    no_hr = rc.running_days(_activities([("2026-10-08", "running", 5.0, [0.0] * 5)]))
    assert pd.isna(no_hr["hard_share"].iloc[0]) and not no_hr["is_hard"].iloc[0]


def test_weekly_totals_show_changes_both_ways_and_flag_ramps() -> None:
    """Every week gets its change on the week before, up or down; only rises above 10% are flagged.

    A week without runs counts as 0 km, so the week after it has no percentage to compare with.
    """
    days = rc.running_days(
        _activities(
            [
                ("2026-09-07", "running", 20.0, EASY),
                ("2026-09-14", "running", 21.0, EASY),  # +5%: shown, not flagged
                ("2026-09-21", "running", 30.0, EASY),  # +43%: flagged
                ("2026-09-28", "running", 15.0, EASY),  # -50%: shown as a decrease
                ("2026-10-12", "running", 10.0, EASY),  # after an empty week: no change
            ]
        )
    )
    totals = rc.weekly_totals(days)
    weeks = {r["week"]: r for r in totals.to_dict("records")}
    assert weeks[date(2026, 9, 14)]["change"] == pytest.approx(0.05)
    assert totals["is_ramp"].tolist() == [False, False, True, False, False, False]
    assert weeks[date(2026, 9, 28)]["change"] == pytest.approx(-0.5)
    assert weeks[date(2026, 10, 5)]["km"] == 0
    assert pd.isna(weeks[date(2026, 10, 12)]["change"])

    two_weeks = _activities([("2026-09-07", "running", 20.0, EASY), ("2026-09-14", "running", 10.0, EASY)])
    fig = rc.year_calendar(two_weeks, _no_health(), 2026)
    week_labels = list(_month(fig, 9)[3].text)
    assert "10.0 km<br>▼ -50%" in week_labels


def test_low_recovery_uses_garmins_own_ratings() -> None:
    """A morning counts as low recovery when readiness is low or poor, or HRV is below its baseline."""
    health = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07"]),
            "readiness_level": ["LOW", "HIGH", "MODERATE"],
            "readiness_score": [31, 80, 60],
            "hrv_status": ["BALANCED", "BALANCED", "LOW"],
            "hrv_last_night_avg": [50, 55, 38],
        }
    )
    low = rc.low_recovery_days(health)
    assert low == {date(2026, 10, 5): "readiness low (31)", date(2026, 10, 7): "HRV below baseline (38 ms)"}


def test_month_title_counts_run_days_and_hard_runs_on_low_recovery_days() -> None:
    """The month line sums up run days by intensity, and how often a hard run fell on a low-recovery day."""
    days = rc.running_days(ACTIVITIES)
    low = {date(2026, 10, 7): "readiness low (31)", date(2026, 10, 20): "readiness poor (12)"}
    summary = rc.summarize_month(days, low, date(2026, 10, 1))
    assert summary == rc.MonthSummary(run_days=2, easy=1, hard=1, low_recovery_days=2, hard_on_low_recovery=1)
    assert summary.title(date(2026, 10, 1)).endswith(
        "2 run days: 1 easy, 1 hard · 2 low-recovery days (1 with a hard run)"
    )


def test_run_circles_show_km_scaled_by_area_with_a_ring_on_hard_days() -> None:
    """Run days carry their distance with one decimal, the longest day gets the largest circle, hard days a ring."""
    _, runs, _, _ = _month(rc.year_calendar(ACTIVITIES, _no_health(), 2026), 10)
    assert list(runs.text) == ["8.2", "10.0"]  # 8.25 rounds half to even, like Python's format
    assert list(runs.marker.size) == [pytest.approx(rc.MAX_DIAMETER * (8.25 / 10) ** 0.5), rc.MAX_DIAMETER]
    assert list(runs.marker.line.width) == [1.5, rc.HARD_RING]  # easy, then hard


def test_months_are_stacked_and_days_line_up_under_their_weekday() -> None:
    """Twelve months below each other, each as tall as its weeks; 1 October 2026 is a Thursday in the first row."""
    fig = rc.year_calendar(ACTIVITIES, _no_health(), 2026)
    assert len(fig.data) == 12 * 4
    assert fig.layout.yaxis3.range == (5.5, -0.5)  # March 2026 spans six week rows
    assert rc._weeks_in_month(date(2027, 2, 1)) == 4
    numbers = _month(fig, 10)[0]
    first = list(numbers.text).index("1")
    assert (numbers.x[first], numbers.y[first]) == (3, 0)


def _no_health() -> pd.DataFrame:
    return pd.DataFrame(columns=["date", "readiness_level", "readiness_score", "hrv_status", "hrv_last_night_avg"])
