"""Goal-based coaching. The athlete states what they are training for, and
Claude assesses their recent Garmin history against what that goal demands:
strengths to keep, weaknesses ranked by how much they hold the goal back
(each with a concrete fix), and a phased plan up to the event date.

The goal itself lives in `garminreader.goal`."""

import logging
from datetime import date
from typing import Any, Literal

import pandas as pd
import streamlit as st
from pydantic import BaseModel, Field

from garminreader.dashboard import claude, weekly
from garminreader.dashboard.ai_insights import csv_block
from garminreader.goal import TrainingGoal

logger = logging.getLogger(__name__)

HISTORY_DAYS = 90
# ---------------------------------------------------------------------------
# Structured output
# ---------------------------------------------------------------------------


class Strength(BaseModel):
    area: str = Field(description="Short name, e.g. 'Aerobic consistency'")
    evidence: str = Field(description="The specific numbers and dates from the data that show this")


class Weakness(BaseModel):
    area: str = Field(description="Short name, e.g. 'Long run too short for a half marathon'")
    priority: Literal["high", "medium", "low"] = Field(description="How much this holds the goal back")
    evidence: str = Field(description="The specific numbers and dates from the data that show this")
    why_it_matters: str = Field(description="Why this limits performance for this particular goal")
    how_to_improve: str = Field(description="Concrete changes to training, with progression over the coming weeks")
    key_session: str = Field(
        description="One specific session to add each week, with duration and intensity (pace or heart rate "
        "derived from the athlete's own data where possible)"
    )


class Phase(BaseModel):
    name: str = Field(description="e.g. 'Base', 'Build', 'Peak', 'Taper'")
    weeks: int = Field(description="Number of weeks in this phase")
    focus: str = Field(description="What this phase develops and why it comes at this point")
    weekly_structure: str = Field(description="A typical week in this phase: sessions, durations and intensities")


class GoalAssessment(BaseModel):
    summary: str = Field(
        description="3-4 sentences: where the athlete stands relative to the goal and whether the target is realistic"
    )
    strengths: list[Strength] = Field(description="2-4 strengths relevant to the goal")
    weaknesses: list[Weakness] = Field(description="3-5 weaknesses, most important first")
    phases: list[Phase] = Field(description="Training phases in order, covering the time until the event")
    risks: list[str] = Field(description="Injury, overtraining or recovery risks visible in the data")
    data_gaps: list[str] = Field(
        description="Things that could not be assessed because the data does not show them (e.g. strength work)"
    )


SYSTEM_PROMPT = """You are an experienced endurance coach and exercise \
physiologist. An athlete has told you what they are training for, and you \
have their real Garmin data: a daily recovery table, every activity in the \
period (including minutes in each heart rate zone), a weekly volume summary, \
their personal heart rate zones, their half marathon and marathon results, \
the trend in Garmin's predicted race times, body weight and composition, and \
a latest-status snapshot.

Work out what this specific goal demands (for example, a half marathon needs \
aerobic volume, a long run close to race duration, threshold work and race \
pace practice; a cycling sportive needs long rides and climbing; a first 5k \
needs consistency more than intensity). Then compare those demands with what \
the data actually shows: weekly volume and its trend, the longest sessions, \
intensity distribution (from heart rate, aerobic and anaerobic training \
effect, and above all time in each heart rate zone: is easy running really \
easy?), pace at a given heart rate, consistency week to week, the ramp rate \
of training load, how recovery (HRV, resting heart rate, sleep, stress) \
responds to harder weeks, past race results and whether predicted race times \
are improving.

Rules:
- Every strength and weakness must cite specific numbers and dates from the data.
- If the data cannot show something (for example strength training or \
mobility that is not logged), list it under data gaps instead of guessing.
- Rank weaknesses by how much they limit this goal, not by how easy they are to fix.
- Express intensities in the athlete's own heart rate zones (with bpm) and \
paces derived from their own activities, not generic zones.
- Respect the athlete's available hours, experience and constraints. Build \
load gradually; flag it if the target looks unrealistic for the time left.
- The phases must add up to the weeks until the event (or the planning \
horizon if there is no event date).

This is training guidance based on data patterns, not medical advice."""


def build_context(
    goal: TrainingGoal,
    daily_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    current_status: dict[str, Any],
    today: date,
    *,
    hr_zones: dict[str, Any] | None = None,
    race_results: pd.DataFrame | None = None,
    race_predictions: pd.DataFrame | None = None,
    body_df: pd.DataFrame | None = None,
) -> str:
    activities = activities_df.drop(columns=["activity_id", "date"], errors="ignore")
    if not activities.empty:
        activities = activities.sort_values("start")
    return "\n".join(
        [
            f"Today is {today.isoformat()}.",
            "\n## What the athlete is training for",
            goal.describe(today),
            "\n## Weekly volume per activity type",
            csv_block(weekly.training_summary(activities_df)),
            "\n## Activity log",
            csv_block(activities),
            "\n## Daily recovery and wellness metrics",
            csv_block(daily_df.sort_values("date") if not daily_df.empty else daily_df),
            "\n## Personal heart rate zones (floor of each zone, bpm)",
            str(hr_zones or "(not available)"),
            "\n## Half marathon and marathon results (all time)",
            csv_block(race_results if race_results is not None else pd.DataFrame()),
            "\n## Garmin's predicted race times, in seconds (weekly, all time)",
            csv_block(weekly.last_per_week(race_predictions) if race_predictions is not None else pd.DataFrame()),
            "\n## Body weight and composition (daily average of weigh-ins)",
            csv_block(body_df if body_df is not None else pd.DataFrame()),
            "\n## Latest status snapshot",
            str(current_status),
        ]
    )


def assess(
    goal: TrainingGoal,
    daily_df: pd.DataFrame,
    activities_df: pd.DataFrame,
    current_status: dict[str, Any],
    today: date,
    *,
    hr_zones: dict[str, Any] | None = None,
    race_results: pd.DataFrame | None = None,
    race_predictions: pd.DataFrame | None = None,
    body_df: pd.DataFrame | None = None,
) -> GoalAssessment:
    context = build_context(
        goal,
        daily_df,
        activities_df,
        current_status,
        today,
        hr_zones=hr_zones,
        race_results=race_results,
        race_predictions=race_predictions,
        body_df=body_df,
    )
    return _assess(context)


@st.cache_data(ttl=60 * 60, max_entries=20, show_spinner=False)
def _assess(context: str) -> GoalAssessment:
    return claude.parse(SYSTEM_PROMPT, context, GoalAssessment)
