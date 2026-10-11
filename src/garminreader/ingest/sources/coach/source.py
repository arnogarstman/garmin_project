"""Workout reviews by Claude, as a source: one raw record per reviewed activity.

Unlike the other sources its input is the warehouse itself. It reviews the activities in
marts.fct_activities that have no review in raw.payloads yet, each against the training and
recovery before it, and yields Claude's answer untouched. dbt models the reviews like any other
raw payload (staging/coach, marts.fct_workout_reviews), so a review is written once and kept.
"""

import csv
import io
import logging
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import duckdb

from garminreader import claude, db
from garminreader.goal import load_goal
from garminreader.ingest.sources.base import RawRecord
from garminreader.ingest.sources.coach.review import PROMPT_VERSION, SYSTEM_PROMPT, WorkoutReview

logger = logging.getLogger(__name__)

ENDPOINT = "workout_review"
# Reviews cover recent workouts only: a review is for the days after a session, and the cap
# bounds the cost of a run that finds a backlog (a first run, or after an outage).
LOOKBACK_DAYS = 7
MAX_PER_RUN = 5
HISTORY_DAYS = 42
RECOVERY_DAYS = 14

_UNREVIEWED = f"""
    select activity_id, activity_date, started_at_local
    from marts.fct_activities a
    where activity_date between ? and ?
      and not exists (
          select 1 from raw.payloads p
          where p.source = 'coach' and p.endpoint = '{ENDPOINT}'
            and (p.params ->> '$.activity_id')::bigint = a.activity_id
      )
    order by started_at_local desc
"""

_WORKOUT = "select * exclude (is_tagged_race) from marts.fct_activities where activity_id = ?"

_HISTORY = """
    select activity_date, activity_name, activity_type, round(distance_km, 2) as km,
           round(duration_min, 1) as min, round(pace_min_per_km, 2) as pace, avg_hr, max_hr,
           aerobic_effect, anaerobic_effect, round(training_load) as training_load,
           round(hr_zone_1_min) as z1, round(hr_zone_2_min) as z2, round(hr_zone_3_min) as z3,
           round(hr_zone_4_min) as z4, round(hr_zone_5_min) as z5
    from marts.fct_activities
    where started_at_local < ? and activity_date >= ?
    order by started_at_local
"""

_RECOVERY = """
    select calendar_date, resting_hr, hrv_last_night_avg as hrv, hrv_status, sleep_score,
           round(sleep_seconds / 3600, 1) as sleep_h, readiness_score, body_battery_highest,
           avg_stress, round(acute_load) as acute_load, round(chronic_load) as chronic_load,
           round(acwr, 2) as acwr, training_status, vo2max
    from marts.fct_daily_health
    where calendar_date between ? and ?
    order by calendar_date
"""

_PREDICTIONS = """
    select calendar_date, predicted_5k_s, predicted_10k_s, predicted_half_marathon_s, predicted_marathon_s
    from marts.fct_race_predictions
    where calendar_date <= ?
    order by calendar_date desc
    limit 1
"""

_ZONES = "select * from marts.rpt_heart_rate_zones"


class CoachSource:
    name = "coach"

    def extract(self, since: date | None = None, until: date | None = None) -> Iterator[RawRecord]:
        """Review the unreviewed activities from `since` (at most LOOKBACK_DAYS back) to `until`,
        newest first and at most MAX_PER_RUN. Without ANTHROPIC_API_KEY it reviews nothing."""
        if not claude.available():
            logger.warning("ANTHROPIC_API_KEY not set; no workout reviews")
            return
        until = until or date.today()
        lookback = until - timedelta(days=LOOKBACK_DAYS)
        since = min(since, lookback) if since else lookback

        with db.connect(read_only=True) as con:
            todo = con.execute(_UNREVIEWED, [since, until]).fetchall()
            if len(todo) > MAX_PER_RUN:
                logger.info("%d workouts to review; reviewing the newest %d this run", len(todo), MAX_PER_RUN)
            reviewed = failed = 0
            for activity_id, activity_date, started_at in todo[:MAX_PER_RUN]:
                prompt = _prompt(con, activity_id, activity_date, started_at)
                try:
                    review = claude.parse(SYSTEM_PROMPT, prompt, WorkoutReview)
                except Exception:
                    # One bad answer must not cost the other reviews; the next run retries it.
                    logger.exception("Could not review activity %s", activity_id)
                    failed += 1
                    continue
                reviewed += 1
                logger.info("Reviewed activity %s: %s", activity_id, review.headline)
                params = {"activity_id": activity_id, "model": claude.MODEL, "prompt_version": PROMPT_VERSION}
                yield RawRecord(endpoint=ENDPOINT, params=params, payload=review.model_dump(mode="json"))
        if failed and not reviewed:
            raise RuntimeError(f"Every workout review failed ({failed}); see the log above")


def _prompt(con: duckdb.DuckDBPyConnection, activity_id: int, activity_date: date, started_at: Any) -> str:
    """The workout and what came before it, as text for Claude."""
    sections = [
        ("The workout to review", _csv(con, _WORKOUT, [activity_id])),
        (
            f"Activities in the {HISTORY_DAYS} days before it",
            _csv(con, _HISTORY, [started_at, activity_date - timedelta(days=HISTORY_DAYS)]),
        ),
        (
            f"Daily recovery and load, the {RECOVERY_DAYS} days up to and including the workout day",
            _csv(con, _RECOVERY, [activity_date - timedelta(days=RECOVERY_DAYS), activity_date]),
        ),
        ("Garmin race predictions on the day (seconds)", _csv(con, _PREDICTIONS, [activity_date])),
        ("Heart rate zone floors (bpm)", _csv(con, _ZONES, [])),
    ]
    goal = load_goal()
    text = "\n\n".join(f"## {title}\n{body or '(no data)'}" for title, body in sections)
    goal_text = goal.describe(activity_date) if goal else "(no goal set)"
    units = "Units: km, minutes, pace in min/km, heart rate in bpm, zone columns in minutes."
    return f"{text}\n\n## The athlete's goal\n{goal_text}\n\n{units}"


def _csv(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> str:
    result = con.execute(sql, params)
    rows = result.fetchall()
    if not rows:
        return ""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([c[0] for c in result.description])
    writer.writerows(rows)
    return out.getvalue().strip()
