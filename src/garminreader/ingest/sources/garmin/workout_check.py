"""Is there a workout on Garmin that the warehouse has not stored yet? `uv run workout-check`.

The frequent scheduled check in refresh.yml runs this and starts the full refresh only when it
prints `new=true`. To keep calls to Garmin few, it asks Garmin nothing outside the training hours
(Amsterdam time) or once today's workout is stored: most days have one, and the next morning's
daily refresh picks up any later one. Otherwise it makes one Garmin call for the newest activity.
It writes nothing but that line to stdout (for $GITHUB_OUTPUT; logs go to stderr). A failed check
prints `new=false` and exits 0, so a broken session fails the daily refresh once instead of every
check.
"""

import logging
import sys
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

from garminreader import db
from garminreader.ingest.sources.garmin import auth

logger = logging.getLogger("workout-check")

TIMEZONE = ZoneInfo("Europe/Amsterdam")
# Local hours in which a check may call Garmin: from 06:00 up to 22:00.
TRAINING_HOURS = range(6, 22)

_STORED = """
    select count(*) from raw.payloads
    where source = 'garmin' and endpoint = 'activity' and (params ->> '$.activity_id')::bigint = ?
"""


def newest_activity(api: Any) -> dict[str, Any] | None:
    """The most recent activity on Garmin Connect, if there is any."""
    activities = api.get_activities(0, 1)
    return activities[0] if isinstance(activities, list) and activities else None


_STORED_ON = """
    select count(*) from raw.payloads
    where source = 'garmin' and endpoint = 'activity' and (payload ->> '$.startTimeLocal')::date = ?
"""


def _count(sql: str, param: Any) -> int:
    if not db.exists():
        return 0
    with db.connect(read_only=True) as con:
        try:
            row = con.execute(sql, [param]).fetchone()
        except duckdb.CatalogException:  # no raw table yet: nothing is stored
            return 0
    return int(row[0]) if row else 0


def is_stored(activity_id: int) -> bool:
    return _count(_STORED, activity_id) > 0


def has_workout_on(day: date) -> bool:
    """Whether a Garmin activity that started on `day` (local time) is stored."""
    return _count(_STORED_ON, day) > 0


def check(
    connect: Callable[[], Any] = auth.connect, now: Callable[[], datetime] = lambda: datetime.now(TIMEZONE)
) -> bool:
    """Whether Garmin's newest activity is missing from the warehouse, asking Garmin only in the
    training hours and only while today's workout is not stored yet."""
    local = now()
    if local.hour not in TRAINING_HOURS:
        logger.info("Outside the training hours (%02d:00 in Amsterdam); not asking Garmin", local.hour)
        return False
    if has_workout_on(local.date()):
        logger.info("Today's workout is already stored; the next daily refresh picks up any other")
        return False
    activity = newest_activity(connect())
    if activity is None:
        logger.info("No activities on Garmin Connect")
        return False
    activity_id = int(activity["activityId"])
    new = not is_stored(activity_id)
    logger.info(
        "Newest activity %s (%s, %s): %s",
        activity_id,
        activity.get("activityName"),
        activity.get("startTimeLocal"),
        "new" if new else "already stored",
    )
    return new


def main() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        new = check()
    except Exception as exc:
        logger.warning("Could not check for a new workout: %s", exc)
        # GitHub shows this line as a warning on the run.
        sys.stderr.write(f"::warning::Workout check failed: {exc}\n")
        new = False
    sys.stdout.write(f"new={'true' if new else 'false'}\n")


if __name__ == "__main__":
    main()
