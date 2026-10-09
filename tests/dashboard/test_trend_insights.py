import pandas as pd

from garminreader.dashboard import trend_insights as ti

DAILY = pd.DataFrame(
    {
        "date": pd.to_datetime(["2026-05-01", "2026-05-02", "2026-05-03"]),
        "resting_hr": [52, 51, 50],
        "vo2max": [48.0, None, 49.0],
    }
)


def test_every_topic_has_a_prompt() -> None:
    """Each topic the tabs can ask about has its own system prompt, so adding a topic without one fails here."""
    assert set(ti.SYSTEM_PROMPTS) == set(ti.Topic)


def test_recovery_context_holds_the_daily_metrics() -> None:
    """The recovery prompt gets the full daily table plus the weekly training summary section."""
    context = ti.build_context(ti.Topic.RECOVERY, daily_df=DAILY)
    assert "## Daily recovery metrics" in context
    assert "resting_hr" in context
    assert "## Weekly training per activity type" in context


def test_body_context_keeps_only_days_with_a_vo2max() -> None:
    """For body composition, VO2 max is passed as its own series without the days Garmin did not estimate it."""
    context = ti.build_context(ti.Topic.BODY, daily_df=DAILY)
    vo2_section = context.split("## VO2 max per day")[1].split("##")[0]
    assert "48.0" in vo2_section and "49.0" in vo2_section
    assert "2026-05-02" not in vo2_section


def test_prediction_context_uses_weekly_predictions_and_weight() -> None:
    """Race predictions are reduced to the last one per week and paired with weight, which drives VO2 max per kg."""
    predictions = pd.DataFrame(
        {"date": pd.to_datetime(["2026-05-04", "2026-05-05"]), "predicted_half_marathon_s": [6900, 6890]}
    )
    body = pd.DataFrame({"date": pd.to_datetime(["2026-05-04"]), "weight_kg": [88.0], "body_fat_pct": [22.0]})
    context = ti.build_context(ti.Topic.RACE_PREDICTIONS, predictions_df=predictions, body_df=body)
    assert "6890" in context and "6900" not in context
    assert "88.0" in context and "22.0" not in context


def test_goal_is_included_when_given_and_missing_data_is_explicit() -> None:
    """The saved goal leads the prompt when there is one; absent tables show '(no data)' instead of raising."""
    context = ti.build_context(ti.Topic.BODY, goal="- Goal: Half marathon")
    assert context.startswith("## What the athlete is training for\n- Goal: Half marathon")
    assert "(no data)" in context
    assert "training for" not in ti.build_context(ti.Topic.BODY)
