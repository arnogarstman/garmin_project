"""Garmin Insights: a Streamlit dashboard on the dbt marts that turns your
activity and recovery data into insights, explanations, and a daily training
suggestion. Run with `uv run dashboard`; data comes from `uv run ingest garmin`
followed by `uv run transform`."""

import logging
from datetime import date, timedelta
from typing import Any

import streamlit as st

from garminreader.dashboard import ai_insights as ai
from garminreader.dashboard import charts, queries, refresh
from garminreader.dashboard import insights as ins
from garminreader.dashboard import training_suggestions as ts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="Garmin Insights", page_icon="🏃", layout="wide")


DIRECTION_ICON = {"up": "📈", "down": "📉", "flat": "➡️", "na": "ℹ️"}
INTENSITY_ICON = {"rest": "🛌", "easy": "🟢", "moderate": "🟡", "hard": "🔴"}
BANNER_BY_LEVEL = {
    "rest": st.error,
    "easy": st.warning,
    "moderate": st.info,
    "hard": st.success,
}
SLEEP_STAGES = ["deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds", "awake_seconds"]


def fmt(value: Any, suffix: str = "", decimals: int = 0) -> str:
    if value is None:
        return "–"
    return f"{value:.{decimals}f}{suffix}"


# --------------------------------------------------------------------------
# Sidebar: range controls and pipeline refresh
# --------------------------------------------------------------------------

with st.sidebar:
    range_choice = st.selectbox("Date range", ["Last 7 days", "Last 30 days", "Last 90 days"], index=1)
    n_days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[range_choice]
    end_date = date.today()
    start_date = end_date - timedelta(days=n_days - 1)

    st.divider()
    if st.button("Refresh from Garmin", help="Runs `ingest garmin` and `transform build`."):
        with st.spinner("Fetching from Garmin and rebuilding models..."):
            try:
                refresh.run_pipeline()
                st.rerun()
            except refresh.RefreshFailed as exc:
                st.error("Refresh failed. Details below and in the terminal log.")
                st.code(str(exc), language="text")

# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

try:
    daily_df = queries.daily_health(start_date, end_date)
    activities_df = queries.activities(start_date, end_date)
    current_status = queries.current_status()
    last_loaded = queries.last_loaded_at()
except queries.WarehouseNotReady:
    st.title("🏃 Garmin Insights")
    st.info(
        "No data yet. Set `GARMIN_EMAIL` and `GARMIN_PASSWORD` in `.env`, then run "
        "`uv run ingest garmin` and `uv run transform` (or click Refresh from Garmin)."
    )
    st.stop()

with st.sidebar:
    if last_loaded is not None:
        st.caption(f"Data last fetched {last_loaded:%Y-%m-%d %H:%M} UTC.")

tab_overview, tab_activities, tab_recovery, tab_insights, tab_suggestions = st.tabs(
    ["Overview", "Activities", "Recovery", "Insights", "Training Suggestions"]
)

# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------

with tab_overview:
    suggestion = ts.generate_suggestion(current_status, daily_df)
    BANNER_BY_LEVEL[suggestion.level](f"**{suggestion.headline}**")

    last_sleep_score = None
    if not daily_df.empty and daily_df["sleep_score"].notna().any():
        last_sleep_score = daily_df.dropna(subset=["sleep_score"]).sort_values("date")["sleep_score"].iloc[-1]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Body Battery", fmt(current_status.get("body_battery_current")))
    c2.metric("Sleep Score (last night)", fmt(last_sleep_score))
    c3.metric("Training Readiness", fmt(current_status.get("readiness_score")))
    c4.metric("Resting HR", fmt(current_status.get("resting_hr"), " bpm"))

    c5, c6, c7 = st.columns(3)
    c5.metric("VO2 Max", fmt(current_status.get("vo2max"), decimals=1))
    c6.metric("Training Status", str(current_status.get("training_status") or "–").title())
    c7.metric("Acute:Chronic Load Ratio", fmt(current_status.get("acwr"), decimals=2))

    with st.expander("Show raw data (debug)"):
        st.write("Current status snapshot", current_status)
        st.write("Daily metrics", daily_df)
        st.write("Activities", activities_df)

# --------------------------------------------------------------------------
# Activities
# --------------------------------------------------------------------------

with tab_activities:
    if activities_df.empty:
        st.info("No activities found in this date range.")
    else:
        display_df = activities_df.sort_values("start", ascending=False)[
            ["start", "name", "type", "distance_km", "duration_min", "avg_hr", "calories", "training_load"]
        ].rename(
            columns={
                "start": "Date",
                "name": "Activity",
                "type": "Type",
                "distance_km": "Distance (km)",
                "duration_min": "Duration (min)",
                "avg_hr": "Avg HR",
                "calories": "Calories",
                "training_load": "Training Load",
            }
        )
        st.dataframe(display_df, width="stretch", hide_index=True)

        weekly = activities_df.dropna(subset=["date"]).copy()
        weekly["week"] = weekly["date"].dt.to_period("W").apply(lambda p: p.start_time)
        weekly_volume = weekly.groupby("week", as_index=False).agg(distance_km=("distance_km", "sum"))

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Weekly distance")
            st.plotly_chart(
                charts.bar_chart(weekly_volume, "week", "distance_km", y_title="km"),
                width="stretch",
            )
        with col_b:
            st.subheader("Average heart rate per activity")
            hr_df = activities_df.dropna(subset=["avg_hr"]).sort_values("start")
            if hr_df.empty:
                st.info("No heart rate data on these activities.")
            else:
                st.plotly_chart(
                    charts.line_chart(hr_df, "start", "avg_hr", y_title="bpm"),
                    width="stretch",
                )

# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------

with tab_recovery:
    if daily_df.empty:
        st.info("No recovery data found in this date range.")
    else:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Resting heart rate")
            rhr_df = daily_df.dropna(subset=["resting_hr"])
            if not rhr_df.empty:
                st.plotly_chart(
                    charts.line_chart(rhr_df, "date", "resting_hr", y_title="bpm"),
                    width="stretch",
                )
            else:
                st.info("No resting heart rate data available for this range.")
        with col_b:
            st.subheader("Sleep score")
            sleep_df = daily_df.dropna(subset=["sleep_score"])
            if not sleep_df.empty:
                st.plotly_chart(
                    charts.line_chart(sleep_df, "date", "sleep_score", y_title="score / 100"),
                    width="stretch",
                )
            else:
                st.info("No sleep score data available for this range.")

        col_c, col_d = st.columns(2)
        with col_c:
            st.subheader("Heart rate variability")
            hrv_df = daily_df.dropna(subset=["hrv_last_night_avg"])
            if not hrv_df.empty:
                st.plotly_chart(
                    charts.line_chart(hrv_df, "date", "hrv_last_night_avg", y_title="ms"),
                    width="stretch",
                )
            else:
                st.info("No HRV data available for this range.")
        with col_d:
            st.subheader("All-day stress")
            stress_df = daily_df.dropna(subset=["avg_stress"])
            if not stress_df.empty:
                st.plotly_chart(
                    charts.line_chart(stress_df, "date", "avg_stress", y_title="stress / 100"),
                    width="stretch",
                )

        st.subheader("Body Battery range")
        bb_df = daily_df.dropna(subset=["body_battery_highest", "body_battery_lowest"])
        if not bb_df.empty:
            st.plotly_chart(
                charts.multi_line_chart(
                    bb_df,
                    "date",
                    {"body_battery_highest": "Highest", "body_battery_lowest": "Lowest"},
                    y_title="/ 100",
                ),
                width="stretch",
            )

        st.subheader("Sleep stages")
        stage_df = daily_df.dropna(subset=SLEEP_STAGES).copy()
        if not stage_df.empty:
            for stage in SLEEP_STAGES:
                stage_df[stage.replace("_seconds", "_hours")] = stage_df[stage] / 3600
            st.plotly_chart(
                charts.stacked_area_chart(
                    stage_df,
                    "date",
                    {
                        "deep_sleep_hours": "Deep",
                        "light_sleep_hours": "Light",
                        "rem_sleep_hours": "REM",
                        "awake_hours": "Awake",
                    },
                    y_title="hours",
                ),
                width="stretch",
            )
        else:
            st.info("No detailed sleep stage data available for this range.")

# --------------------------------------------------------------------------
# Insights
# --------------------------------------------------------------------------

with tab_insights:
    all_insights = ins.build_all_insights(daily_df, activities_df, current_status)
    if not all_insights:
        st.info("Not enough data yet to generate insights; try a longer date range.")

    st.subheader("🤖 AI Coach")
    if not ai.available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to enable an AI-written analysis of your raw data.")
    elif daily_df.empty:
        st.caption("Needs recovery data in this date range to analyze.")
    else:
        if st.button("Generate AI synthesis"):
            with st.spinner("Asking Claude to analyze your data..."):
                try:
                    narrative = ai.generate_narrative(daily_df, activities_df, current_status)
                    st.session_state["ai_narrative"] = narrative
                except Exception as e:
                    st.error(f"AI synthesis failed: {e}")
        if st.session_state.get("ai_narrative"):
            with st.container(border=True):
                st.write(st.session_state["ai_narrative"])

    st.divider()
    for insight in all_insights:
        with st.container(border=True):
            st.markdown(f"### {DIRECTION_ICON[insight.direction]} {insight.title}")
            st.caption(insight.explanation)
            st.write(insight.finding)

# --------------------------------------------------------------------------
# Training suggestions
# --------------------------------------------------------------------------

with tab_suggestions:
    suggestion = ts.generate_suggestion(current_status, daily_df)
    BANNER_BY_LEVEL[suggestion.level](f"**{suggestion.headline}**")

    st.subheader("Why")
    for reason in suggestion.reasons:
        st.markdown(f"- {reason}")

    st.subheader("Suggested plan")
    for item in suggestion.plan:
        st.markdown(f"- {item}")

    st.caption(
        "This is a rule-based suggestion from your recent Garmin metrics, not "
        "medical or coaching advice. Always listen to your body."
    )

    st.divider()
    st.subheader("🤖 AI 7-day training plan")

    if not ai.available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to generate a personalized week-ahead schedule.")
    elif daily_df.empty:
        st.caption("Needs recovery data in this date range to build a plan.")
    else:
        if st.button("Generate 7-day plan"):
            with st.spinner("Asking Claude to build your week..."):
                try:
                    st.session_state["ai_training_plan"] = ai.generate_training_plan(
                        daily_df, activities_df, current_status, date.today()
                    )
                except Exception as e:
                    st.error(f"Plan generation failed: {e}")

        plan: ai.TrainingPlan | None = st.session_state.get("ai_training_plan")
        if plan:
            st.write(plan.summary)
            cols = st.columns(7)
            for day_col, day in zip(cols, plan.days, strict=False):
                with day_col, st.container(border=True):
                    st.markdown(f"**{day.day_of_week[:3]}**")
                    st.caption(day.date)
                    st.markdown(f"{INTENSITY_ICON.get(day.intensity.lower(), '⚪')} **{day.intensity.title()}**")
                    st.write(day.focus)
                    if day.duration_min:
                        st.caption(f"{day.duration_min} min")
            for day in plan.days:
                with st.expander(f"{day.day_of_week} {day.date}: {day.focus}"):
                    st.write(day.details)
                    st.caption(f"Why: {day.rationale}")
            st.caption(
                "AI-generated from your recent training and recovery data, not medical or professional coaching advice."
            )
