"""Is there a workout on Garmin that the warehouse has not stored yet? `uv run workout-check`.

The frequent scheduled check in refresh.yml runs this and starts the full refresh only when it
prints `new=true`: one Garmin call for the newest activity, one query on raw.payloads. It writes
nothing but that line to stdout (for $GITHUB_OUTPUT; logs go to stderr). A failed check prints
`new=false` and exits 0, so a broken session fails the daily refresh once instead of every check.
"""

import logging
import sys
from collections.abc import Callable
from typing import Any

import duckdb

from garminreader import db
from garminreader.ingest.sources.garmin import auth

logger = logging.getLogger("workout-check")

_STORED = """
    select count(*) from raw.payloads
    where source = 'garmin' and endpoint = 'activity' and (params ->> '$.activity_id')::bigint = ?
"""


def newest_activity(api: Any) -> dict[str, Any] | None:
    """The most recent activity on Garmin Connect, if there is any."""
    activities = api.get_activities(0, 1)
    return activities[0] if isinstance(activities, list) and activities else None


def is_stored(activity_id: int) -> bool:
    if not db.exists():
        return False
    with db.connect(read_only=True) as con:
        try:
            row = con.execute(_STORED, [activity_id]).fetchone()
        except duckdb.CatalogException:  # no raw table yet: nothing is stored
            return False
    return bool(row and row[0])


def check(connect: Callable[[], Any] = auth.connect) -> bool:
    """Whether Garmin's newest activity is missing from the warehouse."""
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
