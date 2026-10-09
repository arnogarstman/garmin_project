"""Garmin Insights: a Streamlit dashboard on the dbt marts that turns your
activity and recovery data into insights, explanations, and a daily training
suggestion. Run with `uv run dashboard`; data comes from `uv run ingest garmin`
followed by `uv run transform`."""

import logging
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
import streamlit as st

from garminreader import config
from garminreader import goal as goals
from garminreader.dashboard import ai_insights as ai
from garminreader.dashboard import charts, claude, formatting, queries, refresh
from garminreader.dashboard import goal_coach as gc
from garminreader.dashboard import insights as ins
from garminreader.dashboard import run_calendar as rc
from garminreader.dashboard import training_suggestions as ts
from garminreader.dashboard import trend_insights as ti

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
PRIORITY_COLOR: dict[str, Literal["red", "orange", "blue"]] = {"high": "red", "medium": "orange", "low": "blue"}
HR_ZONES = {f"hr_zone_{i}_min": f"Zone {i}" for i in range(1, 6)}
RACE_DISTANCES = {"Half marathon": "predicted_half_marathon_s", "Marathon": "predicted_marathon_s"}
VERDICT_COLOR: dict[str, Literal["green", "orange", "red"]] = {
    "going well": "green",
    "mixed": "orange",
    "needs attention": "red",
}
PREDICTION_METHOD = """
**Where the numbers come from**

- **VO2 max is the starting point.** After outdoor runs with heart rate and GPS, your watch
  compares your pace with your heart rate to estimate your running VO2 max: how much oxygen
  your body can use per kg per minute. Garmin turns that into a time for each distance. A
  higher VO2 max gives a faster prediction at every distance.
- **Body weight counts.** VO2 max is measured per kg, so losing weight raises it, and with it
  your predictions, even when your heart and lungs have not changed.
- **Training history counts too.** According to Garmin, newer watches also look at your recent
  running volume and long runs. That mostly affects the half marathon and marathon: without
  endurance training, those predictions stay more conservative.

**What the prediction assumes**

That you have trained for the distance, pace the race evenly, and run a flat course in good
conditions. Hills, heat, wind or a missing long-run build make the real result slower. The
marathon prediction is often optimistic for runners who do not regularly run 25-30 km.
"""
SLEEP_STAGES = ["deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds", "awake_seconds"]


def _none_if_nan(value: Any) -> Any:
    return None if pd.isna(value) else value


def ai_trend_section(topic: ti.Topic, title: str, context: str, has_data: bool) -> None:
    """A button that asks Claude how things are going for one topic, and the answer.

    The answer is kept per topic and only shown while its input data is unchanged, so
    switching the date range never shows an answer about a different period.
    """
    st.subheader(f":material/auto_awesome: {title}")
    if not claude.available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to get an AI read of this data.")
        return
    if not has_data:
        st.caption("Needs data in this date range.")
        return
    state_key = f"trend_insight_{topic}"
    if st.button("Ask Claude", key=f"trend_button_{topic}", icon=":material/psychology:"):
        with st.spinner("Claude is looking at your data. This can take a minute..."):
            try:
                st.session_state[state_key] = (context, ti.generate(topic, context))
            except Exception as e:
                st.error(f"AI insight failed: {e}")
    stored: tuple[str, ti.TrendInsight] | None = st.session_state.get(state_key)
    if stored is None or stored[0] != context:
        return
    insight = stored[1]
    with st.container(border=True):
        st.badge(insight.verdict, color=VERDICT_COLOR[insight.verdict])
        st.markdown(f"**{insight.headline}**")
        for observation in insight.observations:
            st.markdown(f"- {observation}")
        st.markdown(f":material/my_location: **Focus:** {insight.focus}")
    st.caption("AI-generated from your Garmin data, not medical advice.")


def weekly_change(df: pd.DataFrame, column: str) -> float:
    """Change between the averages of the first and last 7 readings, so one noisy day does not skew it."""
    values = df[column].dropna()
    return float(values.tail(7).mean() - values.head(7).mean())


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
    if config.is_demo():
        st.info(
            "**Demo data.** A simulated runner, generated by `uv run synthesize`. No real person's "
            "data is shown, and refreshing from Garmin is disabled.",
            icon=":material/science:",
        )
    elif st.button("Refresh from Garmin", help="Runs `ingest garmin` and `transform build`."):
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
    body_df = queries.daily_body(start_date, end_date)
    hr_zones = queries.heart_rate_zones()
    race_results_df = queries.race_results()
    race_predictions_df = queries.race_predictions()
except queries.WarehouseNotReady:
    st.title("🏃 Garmin Insights")
    if config.is_demo():
        st.info("No demo data yet. Run `uv run synthesize` and then `uv run transform` with `DATA_PROFILE=demo`.")
    else:
        st.info(
            "No data yet. Set `GARMIN_EMAIL` and `GARMIN_PASSWORD` in `.env`, then run "
            "`uv run ingest garmin` and `uv run transform` (or click Refresh from Garmin)."
        )
    st.stop()

with st.sidebar:
    if last_loaded is not None:
        st.caption(f"Data last fetched {last_loaded:%Y-%m-%d %H:%M} UTC.")

goal = goals.load_goal()
goal_text_for_ai = goal.describe(date.today()) if goal else None

(
    tab_overview,
    tab_activities,
    tab_calendar,
    tab_recovery,
    tab_body,
    tab_races,
    tab_insights,
    tab_suggestions,
    tab_goal,
) = st.tabs(
    [
        "Overview",
        "Activities",
        "Running calendar",
        "Recovery",
        "Body",
        "Races",
        "Insights",
        "Training Suggestions",
        "Goal Coach",
    ]
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

        st.subheader("Time in heart rate zones per week")
        zone_week = weekly.groupby("week", as_index=False)[list(HR_ZONES)].sum()
        if zone_week[list(HR_ZONES)].to_numpy().sum() == 0:
            st.info("No heart rate zone data on these activities.")
        else:
            st.plotly_chart(charts.stacked_bar_chart(zone_week, "week", HR_ZONES, y_title="minutes"), width="stretch")
            if hr_zones:
                floors = [hr_zones[f"zone_{i}_floor_bpm"] for i in range(1, 6)] + [hr_zones["max_hr_bpm"]]
                ranges = ", ".join(f"zone {i + 1}: {floors[i]}-{floors[i + 1] - 1}" for i in range(5))
                st.caption(f"Your zones in bpm ({ranges}). Most easy running belongs in zones 1 and 2.")

# --------------------------------------------------------------------------
# Running calendar
# --------------------------------------------------------------------------

with tab_calendar:
    run_years = queries.activity_years()
    calendar_year = date.today().year
    if len(run_years) > 1:
        calendar_year = (
            st.segmented_control(
                "Year",
                run_years,
                default=calendar_year if calendar_year in run_years else run_years[-1],
                key="run_year",
            )
            or calendar_year
        )
    year_start, year_end = date(calendar_year, 1, 1), date(calendar_year, 12, 31)
    year_activities = queries.activities(year_start, year_end)
    run_days = rc.running_days(year_activities)
    if run_days.empty:
        st.info(f"No runs in {calendar_year}.")
    else:
        hard = int(run_days["is_hard"].sum())
        st.caption(
            f"{calendar_year}: {int(run_days['runs'].sum())} runs on {len(run_days)} days, "
            f"{run_days['km'].sum():.1f} km in total; {hard} of the run days were hard. "
            "Always the whole year, whatever the date range in the sidebar. Hover a day for details."
        )
        st.markdown(
            ":green[**●**] easy run (mostly heart rate zones 1-2), size follows the distance  \n"
            "**◉** hard run (half or more of the time in zone 3 or higher)  \n"
            ":red[**•**] low recovery that morning (readiness low or poor, or HRV below baseline)  \n"
            "**▲ / ▼** weekly total and its change on the week before; :orange[**orange**] when more than 10% up"
        )
        st.plotly_chart(
            rc.year_calendar(year_activities, queries.daily_health(year_start, year_end), calendar_year),
            width="content",
            config={"displayModeBar": False},
        )

# --------------------------------------------------------------------------
# Recovery
# --------------------------------------------------------------------------

with tab_recovery:
    ai_trend_section(
        ti.Topic.RECOVERY,
        "How is your recovery going?",
        ti.build_context(ti.Topic.RECOVERY, daily_df=daily_df, activities_df=activities_df, goal=goal_text_for_ai),
        has_data=not daily_df.empty,
    )
    st.divider()
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
# Body
# --------------------------------------------------------------------------

with tab_body:
    ai_trend_section(
        ti.Topic.BODY,
        "How is your body composition going?",
        ti.build_context(
            ti.Topic.BODY, daily_df=daily_df, activities_df=activities_df, body_df=body_df, goal=goal_text_for_ai
        ),
        has_data=not body_df.empty or bool(not daily_df.empty and daily_df["vo2max"].notna().any()),
    )
    st.divider()
    if body_df.empty:
        st.info(
            "No weigh-ins in this date range. Weight and body composition come from a Garmin "
            "scale or from entries made in the Garmin Connect app."
        )
    else:
        latest = body_df.iloc[-1]
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Weight",
            fmt(latest["weight_kg"], " kg", 1),
            delta=f"{weekly_change(body_df, 'weight_kg'):+.1f} kg in range",
            help="Average of the last 7 days with a weigh-in against the first 7, so one heavy day does not skew it.",
            delta_color="off",
        )
        c2.metric("Body fat", fmt(_none_if_nan(latest["body_fat_pct"]), "%", 1))
        c3.metric("Muscle mass", fmt(_none_if_nan(latest["muscle_mass_kg"]), " kg", 1))

        trend = body_df.set_index("date")["weight_kg"].rolling("7D").mean().rename("weight_7d").reset_index()
        st.subheader("Weight")
        st.plotly_chart(
            charts.multi_line_chart(
                body_df.merge(trend, on="date"),
                "date",
                {"weight_kg": "Daily", "weight_7d": "7-day average"},
                y_title="kg",
            ),
            width="stretch",
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Body fat")
            fat_df = body_df.dropna(subset=["body_fat_pct"])
            if fat_df.empty:
                st.info("No body fat readings in this range.")
            else:
                st.plotly_chart(charts.line_chart(fat_df, "date", "body_fat_pct", y_title="%"), width="stretch")
        with col_b:
            st.subheader("Muscle mass")
            muscle_df = body_df.dropna(subset=["muscle_mass_kg"])
            if muscle_df.empty:
                st.info("No muscle mass readings in this range.")
            else:
                st.plotly_chart(charts.line_chart(muscle_df, "date", "muscle_mass_kg", y_title="kg"), width="stretch")

    st.subheader("VO2 max")
    vo2_df = daily_df.dropna(subset=["vo2max"]) if not daily_df.empty else daily_df
    if vo2_df.empty:
        st.info("No VO2 max estimates in this date range.")
    else:
        st.plotly_chart(charts.line_chart(vo2_df, "date", "vo2max", y_title="ml/kg/min"), width="stretch")

# --------------------------------------------------------------------------
# Races
# --------------------------------------------------------------------------

with tab_races:
    st.caption("All-time history; not limited to the date range in the sidebar.")
    cols = st.columns(len(RACE_DISTANCES))
    for col, (distance, prediction_col) in zip(cols, RACE_DISTANCES.items(), strict=True):
        races = race_results_df[race_results_df["race_distance"] == distance]
        with col, st.container(border=True):
            st.markdown(f"**{distance}**")
            if races.empty:
                st.caption("No results yet.")
            else:
                last = races.iloc[-1]
                st.metric(
                    "Personal best",
                    formatting.duration(races["finish_time_s"].min()),
                    delta=(
                        f"{formatting.signed_duration(-last['improvement_vs_first_s'])} since your first"
                        if len(races) > 1
                        else None
                    ),
                    delta_color="inverse",
                )
                latest_time = formatting.duration(last["finish_time_s"])
                st.caption(f"{len(races)} result(s); latest {last['date']:%d %b %Y} in {latest_time}")
            predicted = race_predictions_df.dropna(subset=[prediction_col])
            if not predicted.empty:
                now = predicted.iloc[-1][prediction_col]
                change = now - predicted.iloc[0][prediction_col]
                st.metric(
                    "Garmin prediction now",
                    formatting.duration(now),
                    delta=f"{formatting.signed_duration(change)} since {predicted.iloc[0]['date']:%b %Y}",
                    delta_color="inverse",
                )

    st.subheader("Results")
    if race_results_df.empty:
        st.info(
            "No half marathon or marathon in your Garmin activities yet. Runs of 20.8-21.9 km or "
            "41.8-43.5 km appear here automatically, with your progression and personal bests."
        )
    else:
        st.plotly_chart(
            charts.time_trend_chart(
                race_results_df.pivot_table(
                    index="date", columns="race_distance", values="finish_time_s"
                ).reset_index(),
                "date",
                {d: d for d in RACE_DISTANCES if d in set(race_results_df["race_distance"])},
                markers=True,
            ),
            width="stretch",
        )
        table = race_results_df.sort_values("date", ascending=False)
        st.dataframe(
            table.assign(
                finish=table["finish_time_s"].map(formatting.duration),
                pace=table["pace_min_per_km"].map(formatting.pace),
                change=table["improvement_vs_previous_s"].map(lambda s: formatting.signed_duration(-s)),
            )[
                [
                    "date",
                    "activity_name",
                    "race_distance",
                    "distance_km",
                    "finish",
                    "pace",
                    "avg_hr",
                    "change",
                    "is_personal_best",
                ]
            ],
            column_config={
                "date": st.column_config.DateColumn("Date"),
                "activity_name": "Activity",
                "race_distance": "Distance",
                "distance_km": st.column_config.NumberColumn("Measured (km)", format="%.2f"),
                "finish": "Time",
                "pace": "Pace",
                "avg_hr": st.column_config.NumberColumn("Avg HR", format="%d"),
                "change": st.column_config.TextColumn("vs previous", help="Negative is faster"),
                "is_personal_best": st.column_config.CheckboxColumn("New PB"),
            },
            hide_index=True,
            width="stretch",
        )

    st.subheader("Predicted race times over time")
    if race_predictions_df.empty:
        st.info("No race predictions from Garmin yet.")
    else:
        st.plotly_chart(
            charts.time_trend_chart(race_predictions_df, "date", {v: k for k, v in RACE_DISTANCES.items()}),
            width="stretch",
        )
        st.caption("Garmin's estimate of what you could run today, based on VO2 max and recent training.")

    st.subheader("How Garmin predicts your race times")
    st.markdown(PREDICTION_METHOD)

    if not race_predictions_df.empty:
        history_start = race_predictions_df["date"].min().date()
        history_daily = queries.daily_health(history_start, end_date)
        history_body = queries.daily_body(history_start, end_date)
        history_activities = queries.activities(history_start, end_date)

        st.markdown("**What changed since your first prediction**")
        first_pred, last_pred = race_predictions_df.iloc[0], race_predictions_df.iloc[-1]
        vo2 = history_daily.dropna(subset=["vo2max"])
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Predicted half marathon",
            formatting.duration(last_pred["predicted_half_marathon_s"]),
            delta=formatting.signed_duration(
                last_pred["predicted_half_marathon_s"] - first_pred["predicted_half_marathon_s"]
            ),
            delta_color="inverse",
        )
        if not vo2.empty:
            c2.metric(
                "VO2 max",
                fmt(vo2["vo2max"].iloc[-1], decimals=1),
                delta=f"{vo2['vo2max'].iloc[-1] - vo2['vo2max'].iloc[0]:+.1f}",
            )
        if not history_body.empty:
            c3.metric(
                "Weight",
                fmt(history_body["weight_kg"].iloc[-1], " kg", 1),
                delta=f"{weekly_change(history_body, 'weight_kg'):+.1f} kg",
                help="Average of the last 7 days with a weigh-in against the first 7.",
                delta_color="inverse",
            )
        recent_runs = history_activities[
            history_activities["type"].str.contains("running", na=False)
            & (history_activities["date"] >= pd.Timestamp(end_date - timedelta(days=27)))
        ]
        c4.metric(
            "Longest run, last 4 weeks",
            fmt(recent_runs["distance_km"].max() if not recent_runs.empty else None, " km", 1),
        )

        ai_trend_section(
            ti.Topic.RACE_PREDICTIONS,
            "Why your predictions changed",
            ti.build_context(
                ti.Topic.RACE_PREDICTIONS,
                daily_df=history_daily,
                activities_df=history_activities,
                body_df=history_body,
                predictions_df=race_predictions_df,
                goal=goal_text_for_ai,
            ),
            has_data=True,
        )

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

    if goal:
        st.caption(f"Aimed at your goal: {goal.goal}. Change it in the Goal Coach tab.")
    if not ai.available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to generate a personalized week-ahead schedule.")
    elif daily_df.empty:
        st.caption("Needs recovery data in this date range to build a plan.")
    else:
        if st.button("Generate 7-day plan"):
            with st.spinner("Asking Claude to build your week..."):
                try:
                    st.session_state["ai_training_plan"] = ai.generate_training_plan(
                        daily_df,
                        activities_df,
                        current_status,
                        date.today(),
                        goal.describe(date.today()) if goal else None,
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

# --------------------------------------------------------------------------
# Goal coach
# --------------------------------------------------------------------------

with tab_goal:
    st.subheader("What are you training for?")
    with st.form("goal_form"):
        goal_text = st.text_area(
            "Goal",
            value=goal.goal if goal else "",
            placeholder="e.g. Half marathon, or a 100 km gravel ride, or get back into running after injury",
        )
        col_a, col_b = st.columns(2)
        target = col_a.text_input(
            "Target (optional)", value=goal.target if goal else "", placeholder="e.g. under 1:45, or just finish"
        )
        event_date = col_b.date_input(
            "Event date (optional)", value=goal.event_date if goal else None, min_value=date.today()
        )
        col_c, col_d = st.columns(2)
        weekly_hours = col_c.number_input(
            "Hours per week available (optional)",
            min_value=1.0,
            max_value=30.0,
            step=0.5,
            value=goal.weekly_hours if goal else None,
        )
        experience = col_d.selectbox(
            "Experience",
            goals.EXPERIENCE_LEVELS,
            index=goals.EXPERIENCE_LEVELS.index(goal.experience) if goal else 1,
        )
        constraints = st.text_area(
            "Constraints, injuries or preferences (optional)",
            value=goal.constraints if goal else "",
            placeholder="e.g. sore left knee, can only train early mornings, long sessions on Sundays",
        )
        if st.form_submit_button("Save goal", icon=":material/flag:"):
            if not goal_text.strip():
                st.error("Describe your goal first.")
            else:
                goals.save_goal(
                    goals.TrainingGoal(
                        goal=goal_text.strip(),
                        target=target.strip(),
                        event_date=event_date if isinstance(event_date, date) else None,
                        weekly_hours=weekly_hours,
                        experience=experience,
                        constraints=constraints.strip(),
                    )
                )
                st.session_state.pop("goal_assessment", None)
                st.rerun()

    st.divider()
    st.subheader("Strengths, weaknesses and plan")

    if goal is None:
        st.info("Save a goal above to get an analysis of your training against it.")
    elif not ai.available():
        st.info("Set `ANTHROPIC_API_KEY` in `.env` to analyze your training against your goal.")
    else:
        st.caption(
            f"Claude compares the last {gc.HISTORY_DAYS} days of your Garmin data (independent of the date "
            "range in the sidebar) with what your goal demands."
        )
        if st.button("Analyze my training", icon=":material/insights:", type="primary"):
            with st.spinner("Claude is analyzing your training against your goal. This can take a minute..."):
                try:
                    history_start = end_date - timedelta(days=gc.HISTORY_DAYS - 1)
                    st.session_state["goal_assessment"] = gc.assess(
                        goal,
                        queries.daily_health(history_start, end_date),
                        queries.activities(history_start, end_date),
                        current_status,
                        date.today(),
                        hr_zones=hr_zones,
                        race_results=race_results_df,
                        race_predictions=race_predictions_df,
                        body_df=queries.daily_body(history_start, end_date),
                    )
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        assessment: gc.GoalAssessment | None = st.session_state.get("goal_assessment")
        if assessment:
            with st.container(border=True):
                st.write(assessment.summary)

            st.markdown("#### :material/trending_up: Strengths")
            for strength in assessment.strengths:
                st.markdown(f"**{strength.area}**: {strength.evidence}")

            st.markdown("#### :material/build: Weaknesses to work on")
            for weakness in assessment.weaknesses:
                with st.container(border=True):
                    st.markdown(f"**{weakness.area}**")
                    st.badge(f"{weakness.priority} priority", color=PRIORITY_COLOR[weakness.priority])
                    st.caption(weakness.evidence)
                    st.markdown(f"**Why it matters:** {weakness.why_it_matters}")
                    st.markdown(f"**How to improve:** {weakness.how_to_improve}")
                    st.markdown(f"**Key session:** {weakness.key_session}")

            st.markdown("#### :material/calendar_month: Plan")
            for phase in assessment.phases:
                with st.expander(f"{phase.name} ({phase.weeks} weeks): {phase.focus}"):
                    st.write(phase.weekly_structure)

            if assessment.risks:
                st.markdown("#### :material/warning: Watch out for")
                for risk in assessment.risks:
                    st.markdown(f"- {risk}")
            if assessment.data_gaps:
                st.markdown("#### :material/help: Not visible in your data")
                for gap in assessment.data_gaps:
                    st.markdown(f"- {gap}")

            st.caption("AI-generated from your Garmin data, not medical or professional coaching advice.")
