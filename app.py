"""Garmin Insights — a Streamlit app that logs into Garmin Connect and turns
your activity + recovery data into insights, explanations, and a daily
training suggestion."""

import logging
from datetime import date, timedelta

import streamlit as st

import ai_insights as ai
import charts
import garmin_client as gc
import garmin_data as gd
import insights as ins
import training_suggestions as ts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="Garmin Insights", page_icon="🏃", layout="wide")

def _secret(key: str) -> str:
    """Read an optional value from .streamlit/secrets.toml, e.g. to prefill
    the login form. Never stores or requires it — just a local convenience
    file that's gitignored and lives only on this machine."""
    try:
        return st.secrets.get(key, "")
    except Exception:
        return ""


DIRECTION_ICON = {"up": "📈", "down": "📉", "flat": "➡️", "na": "ℹ️"}
INTENSITY_ICON = {"rest": "🛌", "easy": "🟢", "moderate": "🟡", "hard": "🔴"}
BANNER_BY_LEVEL = {
    "rest": st.error,
    "easy": st.warning,
    "moderate": st.info,
    "hard": st.success,
}

# --------------------------------------------------------------------------
# Session state / auth
# --------------------------------------------------------------------------

st.session_state.setdefault("api", None)
st.session_state.setdefault("display_name", None)
st.session_state.setdefault("pending_mfa_api", None)
st.session_state.setdefault("resume_attempted", False)

if not st.session_state.api and not st.session_state.resume_attempted:
    st.session_state.resume_attempted = True
    resumed = gc.try_resume_session()
    if resumed is not None:
        st.session_state.api = resumed
        st.session_state.display_name = resumed.display_name


def render_login() -> None:
    st.title("🏃 Garmin Insights")
    st.caption(
        "Connect your Garmin account to see insights, explanations, and "
        "training suggestions built from your own data."
    )

    if st.session_state.pending_mfa_api is not None:
        st.subheader("Two-factor verification")
        with st.form("mfa_form"):
            code = st.text_input("Enter the verification code Garmin sent you")
            submitted = st.form_submit_button("Verify")
        if submitted:
            try:
                gc.complete_mfa(st.session_state.pending_mfa_api, code)
                st.session_state.api = st.session_state.pending_mfa_api
                st.session_state.display_name = st.session_state.api.display_name
                st.session_state.pending_mfa_api = None
                st.rerun()
            except Exception as e:
                st.error(f"Verification failed: {e}")
        return

    with st.form("login_form"):
        email = st.text_input("Garmin email", value=_secret("garmin_email"))
        password = st.text_input(
            "Garmin password", type="password", value=_secret("garmin_password")
        )
        submitted = st.form_submit_button("Log in")

    if submitted:
        if not email or not password:
            st.error("Enter both email and password.")
        else:
            try:
                with st.spinner("Logging in..."):
                    api, status = gc.begin_login(email, password)
                if status == "mfa":
                    st.session_state.pending_mfa_api = api
                    st.rerun()
                else:
                    st.session_state.api = api
                    st.session_state.display_name = api.display_name
                    st.rerun()
            except gc.GarminConnectAuthenticationError:
                st.error("Login failed — check your email and password.")
            except Exception as e:
                st.error(f"Login failed: {e}")

    st.info(
        "Your credentials go directly to Garmin and aren't stored by this app. "
        "A session token is cached locally in `.garmin_tokens/` so you won't "
        "need to log in again on this machine. To avoid retyping your email/"
        "password on the first login, copy `.streamlit/secrets.toml.example` "
        "to `.streamlit/secrets.toml` (gitignored) to prefill this form."
    )


if not st.session_state.api:
    render_login()
    st.stop()

api = st.session_state.api
display_name = st.session_state.display_name

# --------------------------------------------------------------------------
# Sidebar: account + range controls
# --------------------------------------------------------------------------

with st.sidebar:
    st.markdown(f"**Logged in as** {api.full_name or display_name}")
    if st.button("Log out"):
        gc.logout()
        st.session_state.api = None
        st.session_state.display_name = None
        st.rerun()

    st.divider()
    range_choice = st.selectbox(
        "Date range", ["Last 7 days", "Last 30 days", "Last 90 days"], index=1
    )
    n_days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[range_choice]
    end_date = date.today()
    start_date = end_date - timedelta(days=n_days - 1)

    if st.button("Refresh data", help="Re-fetch today, yesterday and activities."):
        gd.clear_recent_cache()
        st.rerun()
    if st.button("Reload full history", help="Re-fetch every day in the range. Slow."):
        st.cache_data.clear()
        st.rerun()
    st.caption(
        f"Today and yesterday refresh automatically every {gd.LIVE_TTL // 60} "
        "minutes. Older days are cached for a week."
    )

# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

fetch_errors = gd.FetchErrors()
progress_bar = st.progress(0.0, text="Loading Garmin data...")
daily_df = gd.build_daily_dataframe(
    api,
    display_name,
    start_date,
    end_date,
    fetch_errors,
    progress=lambda p: progress_bar.progress(p, text=f"Loading Garmin data... {int(p * 100)}%"),
)
progress_bar.empty()

activities_df = gd.get_activities(api, display_name, start_date, end_date, fetch_errors)
current_status = gd.get_current_status(api, display_name, end_date, fetch_errors)

if fetch_errors.failures:
    st.warning(
        f"{len(fetch_errors.failures)} Garmin requests failed, so some values may "
        "be missing. Failed requests are not cached: click Refresh data to retry. "
        "Details are in the terminal log."
    )
    with st.expander("Failed requests"):
        st.write(fetch_errors.failures)

tab_overview, tab_activities, tab_recovery, tab_insights, tab_suggestions = st.tabs(
    ["Overview", "Activities", "Recovery", "Insights", "Training Suggestions"]
)

# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------

with tab_overview:
    suggestion = ts.generate_suggestion(current_status, daily_df)
    BANNER_BY_LEVEL[suggestion.level](f"**{suggestion.headline}**")

    def fmt(value, suffix="", decimals=0):
        if value is None:
            return "–"
        return f"{value:.{decimals}f}{suffix}"

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
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        weekly = activities_df.dropna(subset=["date"]).copy()
        weekly["week"] = weekly["date"].dt.to_period("W").apply(lambda p: p.start_time)
        weekly_volume = weekly.groupby("week", as_index=False)["distance_km"].sum()

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Weekly distance")
            st.plotly_chart(
                charts.bar_chart(weekly_volume, "week", "distance_km", y_title="km"),
                use_container_width=True,
            )
        with col_b:
            st.subheader("Average heart rate per activity")
            hr_df = activities_df.dropna(subset=["avg_hr"]).sort_values("start")
            if hr_df.empty:
                st.info("No heart rate data on these activities.")
            else:
                st.plotly_chart(
                    charts.line_chart(hr_df, "start", "avg_hr", y_title="bpm"),
                    use_container_width=True,
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
                    use_container_width=True,
                )
            else:
                st.info("No resting heart rate data available for this range.")
        with col_b:
            st.subheader("Sleep score")
            sleep_df = daily_df.dropna(subset=["sleep_score"])
            if not sleep_df.empty:
                st.plotly_chart(
                    charts.line_chart(sleep_df, "date", "sleep_score", y_title="score / 100"),
                    use_container_width=True,
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
                    use_container_width=True,
                )
            else:
                st.info("No HRV data available for this range.")
        with col_d:
            st.subheader("All-day stress")
            stress_df = daily_df.dropna(subset=["avg_stress"])
            if not stress_df.empty:
                st.plotly_chart(
                    charts.line_chart(stress_df, "date", "avg_stress", y_title="stress / 100"),
                    use_container_width=True,
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
                use_container_width=True,
            )

        st.subheader("Sleep stages")
        stage_df = daily_df.dropna(
            subset=["deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds", "awake_seconds"]
        ).copy()
        if not stage_df.empty:
            for col in ["deep_sleep_seconds", "light_sleep_seconds", "rem_sleep_seconds", "awake_seconds"]:
                stage_df[col.replace("_seconds", "_hours")] = stage_df[col] / 3600
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
                use_container_width=True,
            )
        else:
            st.info("No detailed sleep stage data available for this range.")

# --------------------------------------------------------------------------
# Insights
# --------------------------------------------------------------------------

with tab_insights:
    all_insights = ins.build_all_insights(daily_df, activities_df, current_status)
    if not all_insights:
        st.info("Not enough data yet to generate insights — try a longer date range.")

    st.subheader("🤖 AI Coach")
    if not ai.available():
        st.info(
            "Add an `anthropic_api_key` to `.streamlit/secrets.toml` (or set "
            "the `ANTHROPIC_API_KEY` environment variable) to enable an AI-"
            "written analysis of your raw data."
        )
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
        st.info(
            "Add an `anthropic_api_key` to `.streamlit/secrets.toml` (or set "
            "the `ANTHROPIC_API_KEY` environment variable) to generate a "
            "personalized week-ahead schedule."
        )
    elif daily_df.empty:
        st.caption("Needs recovery data in this date range to build a plan.")
    else:
        if st.button("Generate 7-day plan"):
            with st.spinner("Asking Claude to build your week..."):
                try:
                    plan = ai.generate_training_plan(
                        daily_df, activities_df, current_status, date.today()
                    )
                    st.session_state["ai_training_plan"] = plan
                except Exception as e:
                    st.error(f"Plan generation failed: {e}")

        plan = st.session_state.get("ai_training_plan")
        if plan:
            st.write(plan.summary)
            cols = st.columns(7)
            for col, day in zip(cols, plan.days):
                with col:
                    with st.container(border=True):
                        st.markdown(f"**{day.day_of_week[:3]}**")
                        st.caption(day.date)
                        st.markdown(
                            f"{INTENSITY_ICON.get(day.intensity.lower(), '⚪')} "
                            f"**{day.intensity.title()}**"
                        )
                        st.write(day.focus)
                        if day.duration_min:
                            st.caption(f"{day.duration_min} min")
            for day in plan.days:
                with st.expander(f"{day.day_of_week} {day.date} — {day.focus}"):
                    st.write(day.details)
                    st.caption(f"Why: {day.rationale}")
            st.caption(
                "AI-generated from your recent training and recovery data — "
                "not medical or professional coaching advice."
            )
