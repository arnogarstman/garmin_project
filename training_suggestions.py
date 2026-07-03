"""Rule-based training recommendation. Every rule is deliberately simple and
transparent — each one contributes a named, explained reason — rather than a
black-box score, so the suggestion can be trusted and second-guessed."""

from dataclasses import dataclass, field

import pandas as pd

LEVELS = ["rest", "easy", "moderate", "hard"]

PLAN_BY_LEVEL = {
    "rest": [
        "Full rest day, or gentle mobility/walking only.",
        "Prioritize sleep tonight — aim for a consistent bed time.",
    ],
    "easy": [
        "Easy Zone 1-2 session, 20-40 min (easy jog, spin, or swim).",
        "Keep effort conversational; skip intervals or hard efforts today.",
    ],
    "moderate": [
        "Normal planned session at moderate effort (Zone 2-3).",
        "Fine to include some tempo work, but hold back on maximal efforts.",
    ],
    "hard": [
        "Green light for your hardest planned session (intervals, long run, race pace).",
        "Good day to test fitness or push volume if that's in your plan.",
    ],
}


@dataclass
class Suggestion:
    level: str
    headline: str
    reasons: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)


def _level_from_score(score: int) -> str:
    if score < 40:
        return "rest"
    if score < 60:
        return "easy"
    if score < 80:
        return "moderate"
    return "hard"


def generate_suggestion(
    current_status: dict, daily_df: pd.DataFrame
) -> Suggestion:
    score = 100
    reasons: list[str] = []

    readiness_score = current_status.get("readiness_score")
    readiness_level = (current_status.get("readiness_level") or "").upper()
    if readiness_score is not None:
        if readiness_score < 25 or readiness_level in {"LOW", "VERY_LOW"}:
            score -= 45
            reasons.append(
                f"Training Readiness is low ({readiness_score}/100"
                + (f", {readiness_level.title()}" if readiness_level else "")
                + "). Garmin's readiness score combines sleep, HRV, stress, "
                "acute training load, and recovery time."
            )
        elif readiness_score < 50:
            score -= 20
            reasons.append(
                f"Training Readiness is moderate ({readiness_score}/100), "
                "suggesting only partial recovery."
            )
        elif readiness_score >= 75:
            reasons.append(
                f"Training Readiness is high ({readiness_score}/100) — you're "
                "well recovered."
            )

    if not daily_df.empty:
        last = daily_df.dropna(subset=["hrv_status"]).sort_values("date")
        if not last.empty:
            hrv_status = str(last["hrv_status"].iloc[-1]).upper()
            if hrv_status in {"UNBALANCED", "LOW"}:
                score -= 15
                reasons.append(
                    f"HRV status is {hrv_status.title()}, meaning your nervous "
                    "system shows signs of incomplete recovery."
                )

        last_sleep = daily_df.dropna(subset=["sleep_score"]).sort_values("date")
        if not last_sleep.empty:
            sleep_score = last_sleep["sleep_score"].iloc[-1]
            if sleep_score < 60:
                score -= 15
                reasons.append(
                    f"Last night's sleep score was low ({sleep_score:.0f}/100)."
                )
            elif sleep_score >= 85:
                reasons.append(
                    f"Last night's sleep score was excellent ({sleep_score:.0f}/100)."
                )

    acwr = current_status.get("acwr")
    if acwr:
        if acwr > 1.5:
            score -= 30
            reasons.append(
                f"Acute:chronic workload ratio is high ({acwr:.2f}), meaning "
                "recent training load has climbed sharply above your usual "
                "load — a known injury-risk pattern."
            )
        elif acwr < 0.8:
            reasons.append(
                f"Acute:chronic workload ratio is low ({acwr:.2f}) — recent "
                "load is below your usual, so there's room to build volume "
                "if you're feeling good."
            )

    training_status = (current_status.get("training_status") or "").upper()
    if training_status == "OVERREACHING":
        score -= 20
        reasons.append(
            "Garmin's training status is Overreaching — recent load is "
            "outpacing recovery."
        )
    elif training_status == "DETRAINING":
        reasons.append(
            "Garmin's training status is Detraining — consistency has "
            "dropped and fitness may start slipping."
        )
    elif training_status in {"PRODUCTIVE", "PEAKING"}:
        reasons.append(f"Garmin's training status is {training_status.title()}.")

    body_battery = current_status.get("body_battery_current")
    if body_battery is not None and body_battery < 25:
        score -= 15
        reasons.append(f"Body Battery is low ({body_battery}/100) right now.")

    score = max(0, min(100, score))
    level = _level_from_score(score)

    headline = {
        "rest": "Take it easy today — your body is asking for recovery.",
        "easy": "Keep today light. Save harder efforts for when you're more recovered.",
        "moderate": "Good to train, but hold back from maximal efforts today.",
        "hard": "You're well recovered — green light for a hard session.",
    }[level]

    if not reasons:
        reasons.append(
            "No red flags in your recent recovery data — recommendation is "
            "based on overall readiness."
        )

    return Suggestion(
        level=level, headline=headline, reasons=reasons, plan=PLAN_BY_LEVEL[level]
    )
