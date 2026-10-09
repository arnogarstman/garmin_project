"""On-demand AI read of how things are going in one area of the dashboard:
recovery, body composition, or Garmin's race predictions. Each topic has its
own prompt and data, and they share one result shape so the tabs render them
the same way. Results are cached per prompt, so reopening a tab is free."""

from collections.abc import Callable
from enum import StrEnum
from typing import Literal

import pandas as pd
import streamlit as st
from pydantic import BaseModel, Field

from garminreader.dashboard import claude, weekly
from garminreader.dashboard.ai_insights import csv_block


class Topic(StrEnum):
    RECOVERY = "recovery"
    BODY = "body"
    RACE_PREDICTIONS = "race_predictions"


class TrendInsight(BaseModel):
    verdict: Literal["going well", "mixed", "needs attention"] = Field(description="Overall direction in this area")
    headline: str = Field(description="One sentence summing up how it is going")
    observations: list[str] = Field(
        description="3-5 findings, most important first, each citing specific numbers and dates from the data"
    )
    focus: str = Field(description="The single most useful thing to do or watch next, concrete and specific")


_SHARED_RULES = """

Rules:
- Cite specific numbers and dates for every observation; compare the start and \
end of the period, and point out turning points.
- Relate the trend to the training in the activity data (volume, intensity, \
hard weeks) where the data supports it; say so when it does not.
- If the data is too sparse to support a conclusion, say that plainly instead \
of forcing one.
- If the athlete's goal is given, judge the trend against what that goal needs.
- Plain language, no jargon without a short explanation. Not medical advice; \
do not diagnose."""

SYSTEM_PROMPTS: dict[Topic, str] = {
    Topic.RECOVERY: """You are an exercise physiologist reviewing one \
athlete's recovery from their Garmin data: a daily table with resting heart \
rate, overnight HRV (with Garmin's baseline range), sleep duration, stages and \
score, all-day stress, body battery, training readiness and acute:chronic \
load ratio, plus a weekly summary of their training.

Assess how recovery is going: whether HRV is within or drifting from its \
baseline, whether resting heart rate is creeping up or down, how sleep \
quantity and quality hold up, and above all whether recovery keeps pace with \
the training load or lags behind it after hard weeks."""
    + _SHARED_RULES,
    Topic.BODY: """You are a sports scientist reviewing one athlete's body \
composition from their Garmin data: daily averages of their scale weigh-ins \
(weight, body fat, muscle mass, body water), their VO2 max estimate over time, \
and a weekly summary of their training.

Assess how it is going: the rate of weight change per week and whether it is \
a sustainable pace, whether the change comes from fat or muscle where the \
scale shows it (and how reliable bioimpedance readings are day to day), and \
how weight relates to VO2 max, which Garmin expresses per kg of body weight. \
Smooth over single-day noise; focus on the trend."""
    + _SHARED_RULES,
    Topic.RACE_PREDICTIONS: """You are a running coach explaining Garmin's \
race time predictions to one athlete. You have their predicted 5K, 10K, half \
marathon and marathon times per week, their VO2 max estimate over time, their \
weight, and a weekly summary of their training (sessions, distance, longest \
session).

Garmin derives the predictions mainly from the running VO2 max estimate, and \
on recent devices also from training history, so longer distances are \
predicted slower when the athlete lacks long runs and volume. Explain why \
their predictions moved the way they did: how much of the change follows \
VO2 max, how much weight change contributes (VO2 max is per kg), and how \
their volume and longest runs line up. Then judge how realistic the half \
marathon and marathon predictions are given their actual long runs, and say \
what would make them achievable."""
    + _SHARED_RULES,
}


def build_context(
    topic: Topic,
    *,
    daily_df: pd.DataFrame | None = None,
    activities_df: pd.DataFrame | None = None,
    body_df: pd.DataFrame | None = None,
    predictions_df: pd.DataFrame | None = None,
    goal: str | None = None,
) -> str:
    """The data for one topic as prompt text; empty or missing tables become '(no data)'."""
    sections: list[tuple[str, pd.DataFrame | None]] = {
        Topic.RECOVERY: [("Daily recovery metrics", daily_df)],
        Topic.BODY: [
            ("Daily body composition (average of the day's weigh-ins)", body_df),
            ("VO2 max per day", _vo2max(daily_df)),
        ],
        Topic.RACE_PREDICTIONS: [
            ("Predicted race times in seconds (last of each week)", _maybe(weekly.last_per_week, predictions_df)),
            ("VO2 max per day", _vo2max(daily_df)),
            ("Weight per day (kg)", body_df[["date", "weight_kg"]] if body_df is not None else None),
        ],
    }[topic]
    sections.append(("Weekly training per activity type", _maybe(weekly.training_summary, activities_df)))

    parts = []
    if goal:
        parts += ["## What the athlete is training for", goal, ""]
    for title, df in sections:
        parts += [f"## {title}", csv_block(df if df is not None else pd.DataFrame()), ""]
    return "\n".join(parts)


@st.cache_data(ttl=60 * 60, max_entries=30, show_spinner=False)
def generate(topic: Topic, context: str) -> TrendInsight:
    return claude.parse(SYSTEM_PROMPTS[topic], context, TrendInsight)


def _vo2max(daily_df: pd.DataFrame | None) -> pd.DataFrame | None:
    if daily_df is None or daily_df.empty:
        return None
    return daily_df.dropna(subset=["vo2max"])[["date", "vo2max"]]


def _maybe(fn: Callable[[pd.DataFrame], pd.DataFrame], df: pd.DataFrame | None) -> pd.DataFrame | None:
    return None if df is None else fn(df)
