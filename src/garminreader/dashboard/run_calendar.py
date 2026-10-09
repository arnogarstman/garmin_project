"""The running calendar: a year of runs as twelve month grids below each other.

Each run day is a green circle (area proportional to the distance, km inside).
On top of that it answers three training questions at a glance:

- Was the run easy or hard? Hard runs (half or more of the time in heart rate
  zone 3 or higher, the usual 80/20 split) get a ring in the text color.
- Is the build-up sensible? Each week row ends with the Monday to Sunday
  total and its change on the week before (up or down), highlighted when it
  is more than 10% up.
- Did you train on a poorly recovered day? A red dot marks mornings with low
  or poor training readiness, or HRV below its baseline (Garmin's own ratings).
"""

from collections.abc import Hashable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from garminreader.dashboard import colors, formatting

RUN_TYPES_PATTERN = "running"  # running, trail_running, treadmill_running, track_running, ...
HARD_SHARE = 0.5  # share of time in zone 3+ from which a run day counts as hard
RAMP_WARNING = 0.10  # weekly increase that gets flagged
LOW_READINESS = ("LOW", "POOR")
LOW_HRV = ("LOW",)

GREEN = "#008300"  # deep enough for white labels (5:1 contrast) on light and dark surfaces
MAX_DIAMETER = 44  # px, for the longest run day of the year
MIN_DIAMETER = 28  # px, so the km label still fits inside short runs
HARD_RING = 3  # px
ROW_HEIGHT = 58  # px per week row, with room for the recovery dot under a circle
MONTH_GAP = 70  # px between months, room for the month title and weekday labels
WIDTH = 700  # px: seven day columns plus the week total, not stretched across a wide screen
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEK_COLUMN = 7.9  # x position of the weekly totals, right of Sunday
DOT_OFFSET = 0.42  # recovery dot below the day centre, in rows

HARD_ZONES = ["hr_zone_3_min", "hr_zone_4_min", "hr_zone_5_min"]
ALL_ZONES = ["hr_zone_1_min", "hr_zone_2_min", *HARD_ZONES]


def running_days(activities_df: pd.DataFrame) -> pd.DataFrame:
    """Per day with at least one run: km, number of runs, minutes, the share of heart
    rate time in zone 3 or higher (None without heart rate data) and whether that makes
    the day hard."""
    runs = activities_df[activities_df["type"].str.contains(RUN_TYPES_PATTERN, na=False)]
    if runs.empty:
        return pd.DataFrame(columns=["day", "km", "runs", "minutes", "hard_share", "is_hard"])
    zones = [c for c in ALL_ZONES if c in runs.columns]
    days = (
        runs.assign(
            day=runs["date"].dt.date, zone_total=runs[zones].sum(axis=1), zone_hard=runs[HARD_ZONES].sum(axis=1)
        )
        .groupby("day", as_index=False)
        .agg(
            km=("distance_km", "sum"),
            runs=("activity_id", "count"),
            minutes=("duration_min", "sum"),
            zone_total=("zone_total", "sum"),
            zone_hard=("zone_hard", "sum"),
        )
    )
    days["hard_share"] = (days["zone_hard"] / days["zone_total"]).where(days["zone_total"] > 0)
    days["is_hard"] = days["hard_share"] >= HARD_SHARE
    return days.drop(columns=["zone_total", "zone_hard"])


def weekly_totals(days: pd.DataFrame) -> pd.DataFrame:
    """Km per Monday-first week, with the change on the week before and a ramp flag."""
    if days.empty:
        return pd.DataFrame(columns=["week", "km", "change", "is_ramp"])
    weeks = (
        days.assign(week=[d - timedelta(days=d.weekday()) for d in days["day"]])
        .groupby("week", as_index=False)
        .agg(km=("km", "sum"))
    )
    full = pd.DataFrame({"week": [weeks["week"].min() + timedelta(weeks=i) for i in range(_span_weeks(weeks))]})
    weeks = full.merge(weeks, on="week", how="left").fillna({"km": 0.0})
    previous = weeks["km"].shift(1)
    weeks["change"] = (weeks["km"] / previous - 1).where(previous > 0)
    weeks["is_ramp"] = weeks["change"] > RAMP_WARNING
    return weeks


def low_recovery_days(daily_df: pd.DataFrame) -> dict[date, str]:
    """Days whose morning recovery was low, with the reason in words."""
    out: dict[date, str] = {}
    for row in daily_df.to_dict("records"):
        reasons = []
        if row["readiness_level"] in LOW_READINESS:
            reasons.append(f"readiness {str(row['readiness_level']).lower()} ({_int(row['readiness_score'])})")
        if row["hrv_status"] in LOW_HRV:
            reasons.append(f"HRV below baseline ({_int(row['hrv_last_night_avg'])} ms)")
        if reasons:
            out[pd.Timestamp(row["date"]).date()] = ", ".join(reasons)
    return out


@dataclass(frozen=True)
class MonthSummary:
    run_days: int
    easy: int
    hard: int
    low_recovery_days: int
    hard_on_low_recovery: int

    def title(self, month: date) -> str:
        if self.run_days == 0:
            return f"<b>{month:%B}</b>"
        days = "day" if self.run_days == 1 else "days"
        parts = [f"{self.run_days} run {days}: {self.easy} easy, {self.hard} hard"]
        if self.low_recovery_days:
            parts.append(f"{self.low_recovery_days} low-recovery days ({self.hard_on_low_recovery} with a hard run)")
        return f"<b>{month:%B}</b>   " + " · ".join(parts)


def summarize_month(days: pd.DataFrame, low: dict[date, str], first: date) -> MonthSummary:
    in_month = days[[d.year == first.year and d.month == first.month for d in days["day"]]]
    low_days = [d for d in low if d.year == first.year and d.month == first.month]
    hard_days = set(in_month.loc[in_month["is_hard"], "day"])
    return MonthSummary(
        run_days=len(in_month),
        easy=int((in_month["hard_share"] < HARD_SHARE).sum()),
        hard=len(hard_days),
        low_recovery_days=len(low_days),
        hard_on_low_recovery=len(hard_days & set(low_days)),
    )


def year_calendar(activities_df: pd.DataFrame, daily_df: pd.DataFrame, year: int) -> go.Figure:
    days = running_days(activities_df)
    by_day = days.set_index("day")
    weeks = {row["week"]: row for row in weekly_totals(days).to_dict("records")}
    low = low_recovery_days(daily_df)
    max_km = float(days["km"].max()) if not days.empty else 1.0
    chrome = colors.chrome()

    firsts = [date(year, m, 1) for m in range(1, 13)]
    n_weeks = [_weeks_in_month(first) for first in firsts]
    plot_height = sum(n_weeks) * ROW_HEIGHT + 11 * MONTH_GAP
    fig = make_subplots(
        rows=12,
        cols=1,
        subplot_titles=[summarize_month(days, low, first).title(first) for first in firsts],
        row_heights=[w * ROW_HEIGHT for w in n_weeks],  # each month as tall as its number of weeks
        vertical_spacing=MONTH_GAP / plot_height,
    )

    for row, first in enumerate(firsts, start=1):
        last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        grid = pd.DataFrame({"day": pd.date_range(first, last).date})
        grid["x"] = [d.weekday() for d in grid["day"]]
        grid["y"] = [(d.day + first.weekday() - 1) // 7 for d in grid["day"]]
        grid = grid.join(by_day, on="day")
        ran = grid.dropna(subset=["km"])
        rest = grid[grid["km"].isna()]
        recovery = grid[grid["day"].isin(low.keys())]

        traces = [
            _day_numbers(rest, low, chrome),
            _run_circles(ran, low, max_km, chrome),
            _recovery_dots(recovery, low),
            _week_totals(first, n_weeks[row - 1], weeks, chrome),
        ]
        for trace in traces:
            fig.add_trace(trace, row=row, col=1)
        fig.update_xaxes(
            range=[-0.6, WEEK_COLUMN + 0.7],
            tickvals=[*range(7), WEEK_COLUMN],
            ticktext=[*WEEKDAYS, "Week"],
            side="top",
            row=row,
            col=1,
        )
        # First week on top.
        fig.update_yaxes(range=[n_weeks[row - 1] - 0.5, -0.5], showticklabels=False, row=row, col=1)

    fig.update_xaxes(showgrid=False, zeroline=False, fixedrange=True, color=chrome["muted"], tickfont=dict(size=11))
    fig.update_yaxes(showgrid=False, zeroline=False, fixedrange=True)
    fig.update_annotations(font=dict(size=13, color=chrome["primary_ink"]), yshift=22, x=0, xanchor="left")
    fig.update_layout(
        width=WIDTH,
        height=plot_height + 60,
        margin=dict(l=10, r=10, t=50, b=10),
        plot_bgcolor=chrome["surface"],
        paper_bgcolor=chrome["surface"],
        font=dict(color=chrome["secondary_ink"]),
        showlegend=False,
        hoverlabel=dict(bgcolor=chrome["surface"]),
    )
    return fig


# -- traces ---------------------------------------------------------------------


def _day_numbers(rest: pd.DataFrame, low: dict[date, str], chrome: dict[str, str]) -> go.Scatter:
    """Day numbers on the days without a run, for orientation."""
    return go.Scatter(
        x=rest["x"],
        y=rest["y"],
        mode="text",
        text=[str(d.day) for d in rest["day"]],
        textfont=dict(size=12, color=chrome["muted"]),
        hovertemplate=[f"{d:%a %d %b}{_low_note(d, low)}<extra></extra>" for d in rest["day"]],
    )


def _run_circles(ran: pd.DataFrame, low: dict[date, str], max_km: float, chrome: dict[str, str]) -> go.Scatter:
    hover = []
    for r in ran.to_dict("records"):
        if pd.isna(r["hard_share"]):
            intensity = "no heart rate data"
        else:
            intensity = f"{'hard' if r['is_hard'] else 'easy'}, {r['hard_share']:.0%} in zone 3+"
        runs = int(r["runs"])
        hover.append(
            f"{r['day']:%a %d %b}: {r['km']:.1f} km in {runs} run{'s' if runs > 1 else ''}, "
            f"{formatting.duration(r['minutes'] * 60)}<br>{intensity}{_low_note(r['day'], low)}<extra></extra>"
        )
    return go.Scatter(
        x=ran["x"],
        y=ran["y"],
        mode="markers+text",
        marker=dict(
            size=[max(MIN_DIAMETER, MAX_DIAMETER * (km / max_km) ** 0.5) for km in ran["km"]],
            color=GREEN,
            opacity=1,
            # Hard days wear a ring in the text color; easy days a thin surface-colored gap.
            line=dict(
                width=[HARD_RING if hard else 1.5 for hard in ran["is_hard"]],
                color=[chrome["primary_ink"] if hard else chrome["surface"] for hard in ran["is_hard"]],
            ),
        ),
        text=[f"{km:.1f}" for km in ran["km"]],
        textfont=dict(size=11, color="#ffffff"),
        hovertemplate=hover,
    )


def _recovery_dots(days: pd.DataFrame, low: dict[date, str]) -> go.Scatter:
    return go.Scatter(
        x=days["x"],
        y=days["y"] + DOT_OFFSET,
        mode="markers",
        marker=dict(size=7, color=colors.status("critical")),
        hovertemplate=[f"{d:%a %d %b}: low recovery<br>{low[d]}<extra></extra>" for d in days["day"]],
    )


def _week_totals(
    first: date, n_weeks: int, weeks: dict[date, dict[Hashable, Any]], chrome: dict[str, str]
) -> go.Scatter:
    """The Monday to Sunday total at the end of each week row (whole weeks, also across a month edge)."""
    monday = first - timedelta(days=first.weekday())
    xs, ys, texts, hovers, font_colors = [], [], [], [], []
    for i in range(n_weeks):
        week = monday + timedelta(weeks=i)
        if week not in weeks or weeks[week]["km"] == 0:
            continue
        # change is NaN when there is no week before to compare with
        km, change, ramp = weeks[week]["km"], weeks[week]["change"], bool(weeks[week]["is_ramp"])
        xs.append(WEEK_COLUMN)
        ys.append(i)
        texts.append(f"{km:.1f} km" + ("" if pd.isna(change) else f"<br>{_arrow(change)} {change:+.0%}"))
        font_colors.append(colors.status("serious") if ramp else chrome["secondary_ink"])
        delta = "" if pd.isna(change) else f", {change:+.0%} on the week before"
        warning = "<br>More than 10% up: a common injury-risk threshold" if ramp else ""
        hovers.append(f"Week of {week:%d %b}: {km:.1f} km{delta}{warning}<extra></extra>")
    return go.Scatter(
        x=xs,
        y=ys,
        mode="text",
        text=texts,
        textfont=dict(size=11, color=font_colors),
        hovertemplate=hovers,
    )


# -- helpers ----------------------------------------------------------------------


def _arrow(change: float) -> str:
    return "▲" if change > 0 else "▼" if change < 0 else "="


def _low_note(day: date, low: dict[date, str]) -> str:
    return f"<br>Low recovery: {low[day]}" if day in low else ""


def _weeks_in_month(first: date) -> int:
    """Number of Monday-first week rows the month spans (4 to 6)."""
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return (last.day + first.weekday() - 1) // 7 + 1


def _span_weeks(weeks: pd.DataFrame) -> int:
    first: date = weeks["week"].min()
    last: date = weeks["week"].max()
    return (last - first).days // 7 + 1


def _int(value: Any) -> str:
    return "-" if value is None or pd.isna(value) else str(int(value))
