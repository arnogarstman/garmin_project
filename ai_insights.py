"""AI-narrated synthesis on top of the raw Garmin data. Claude gets the
actual daily metrics and activity log (as CSV) plus the latest status
snapshot, and does its own trend/correlation analysis rather than just
restating the rule-based findings in `insights.py`."""

import os
from datetime import date, timedelta

import anthropic
import pandas as pd
import streamlit as st
from pydantic import BaseModel, Field

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are an exercise physiologist reviewing one athlete's \
raw Garmin data: a daily recovery/wellness table, an activity log, and a \
latest-status snapshot. All of it comes directly from their device — treat \
every number as real and accurate.

Analyze trends and correlations yourself: look at how resting heart rate, \
HRV, sleep score, stress, and body battery move together or diverge over \
the period, and how training volume/intensity from the activity log lines \
up with those recovery signals. Call out the most likely explanation for \
what you see, and flag anything that warrants attention. If the data is \
too sparse or noisy to support a clear story, say so plainly rather than \
forcing a narrative.

Write 150-300 words, plain prose, no headers or bullet lists. Cite the \
specific numbers and dates you're basing conclusions on. Do not give \
medical advice or diagnose anything. End with the single most useful \
thing for the athlete to pay attention to next."""


def _api_key() -> str | None:
    try:
        key = st.secrets.get("anthropic_api_key", "")
    except Exception:
        key = ""
    return key or os.environ.get("ANTHROPIC_API_KEY")


def available() -> bool:
    return bool(_api_key())


def _csv(df: pd.DataFrame) -> str:
    if df.empty:
        return "(no data)"
    return df.to_csv(index=False)


def _build_context(
    daily_df: pd.DataFrame, activities_df: pd.DataFrame, current_status: dict
) -> str:
    parts = [
        "## Daily recovery/wellness metrics (one row per day)",
        _csv(daily_df.sort_values("date")),
        "\n## Activity log",
        _csv(
            activities_df.sort_values("start")[
                [
                    "start",
                    "name",
                    "type",
                    "distance_km",
                    "duration_min",
                    "avg_hr",
                    "max_hr",
                    "calories",
                    "aerobic_effect",
                    "training_load",
                ]
            ]
            if not activities_df.empty
            else activities_df
        ),
        "\n## Latest status snapshot",
        str(current_status),
    ]
    return "\n".join(parts)


@st.cache_data(ttl=15 * 60, show_spinner=False)
def generate_narrative(
    daily_df: pd.DataFrame, activities_df: pd.DataFrame, current_status: dict
) -> str:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("No Anthropic API key configured.")

    client = anthropic.Anthropic(api_key=api_key)
    context = _build_context(daily_df, activities_df, current_status)

    response = client.messages.create(
        model=MODEL,
        max_tokens=1536,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")


# ---------------------------------------------------------------------------
# 7-day AI training plan (structured output)
# ---------------------------------------------------------------------------

PLAN_SYSTEM_PROMPT = """You are an exercise physiologist and coach building \
a concrete, personalized 7-day training schedule for one athlete, based on \
their real Garmin data: a daily recovery/wellness table, their recent \
activity log, and a latest-status snapshot. Treat every number as real and \
accurate.

Base the plan on their actual recent training load, recovery trends (HRV, \
sleep, resting heart rate, stress, body battery), and the sport(s) they \
actually do (infer this from the activity log — don't invent a sport they \
don't do). Vary intensity across the week in a way that responds to their \
current recovery state — don't just repeat the same session every day, and \
don't prescribe hard days back to back unless their data supports it. \
Build in at least one rest or easy day if their recent training load or \
recovery signals are trending down.

For each of the 7 days, give a specific, actionable session — not vague \
advice like "listen to your body." "Rest" is a valid and often correct \
session. Tie the rationale for each day to specific numbers from the data \
you were given.

This is a training suggestion based on data patterns, not medical or \
professional coaching advice."""


class DayPlan(BaseModel):
    date: str = Field(description="ISO date (YYYY-MM-DD) for this day, matching the date given in the prompt")
    day_of_week: str = Field(description="e.g. Monday")
    intensity: str = Field(description="One of: rest, easy, moderate, hard")
    focus: str = Field(description="Short session title, e.g. 'Easy Zone 2 run' or 'Full rest'")
    duration_min: int = Field(description="Planned duration in minutes; 0 for full rest")
    details: str = Field(description="Specific, actionable guidance for this session")
    rationale: str = Field(description="Why this session on this day, citing specific numbers from the athlete's data")


class TrainingPlan(BaseModel):
    summary: str = Field(description="2-3 sentence overview of the week's plan and the reasoning behind its shape")
    days: list[DayPlan] = Field(description="Exactly 7 entries, one per day, in chronological order")


@st.cache_data(ttl=15 * 60, show_spinner=False)
def generate_training_plan(
    daily_df: pd.DataFrame, activities_df: pd.DataFrame, current_status: dict, start: date
) -> TrainingPlan:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("No Anthropic API key configured.")

    client = anthropic.Anthropic(api_key=api_key)
    context = _build_context(daily_df, activities_df, current_status)
    plan_days = [start + timedelta(days=i) for i in range(7)]
    date_list = "\n".join(f"- {d.isoformat()} ({d.strftime('%A')})" for d in plan_days)
    context += f"\n\n## Build the plan for exactly these 7 dates\n{date_list}"

    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        system=PLAN_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": context}],
        output_format=TrainingPlan,
    )
    return response.parsed_output
