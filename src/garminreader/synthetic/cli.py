"""Build the demo warehouse from a simulated athlete: `uv run synthesize`.

Only runs with DATA_PROFILE=demo. The demo raw data is a fixture, so it is
deleted and rewritten on every run; the period always ends today, which keeps
the demo looking current. Follow with `uv run transform`.
"""

import argparse
import logging
from datetime import UTC, date, datetime, timedelta

from garminreader import config
from garminreader.goal import TrainingGoal, save_goal
from garminreader.ingest import storage
from garminreader.synthetic import athlete, payloads

logger = logging.getLogger("synthesize")

DEMO_GOAL = TrainingGoal(
    goal="Half marathon",
    target="under 1:40",
    weekly_hours=5,
    experience="Intermediate",
    constraints="Long runs on Sundays",
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="synthesize", description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=365, help="length of the simulated period (default 365)")
    parser.add_argument("--seed", type=int, default=42, help="random seed; same seed and end date, same data")
    parser.add_argument("--end", type=date.fromisoformat, default=None, help="last simulated day (default today)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not config.is_demo():
        parser.error("synthesize only writes the demo warehouse; run it with DATA_PROFILE=demo")
    if args.days < 60:
        parser.error("--days must be at least 60 for the simulated story to fit")

    days, activities = build(end=args.end or date.today(), days=args.days, seed=args.seed)
    logger.info("Simulated %d days and %d activities into %s", days, activities, config.database())
    logger.info("Next: build the models with `DATA_PROFILE=demo uv run transform`")


def build(end: date, days: int = 365, seed: int = 42) -> tuple[int, int]:
    """Replace the demo raw data with a freshly simulated athlete, and save the demo goal.
    Returns the number of simulated days and activities."""
    if not config.is_demo():
        raise RuntimeError("synthetic data only goes into the demo profile (DATA_PROFILE=demo)")
    states = athlete.simulate(end=end, days=days, seed=seed)
    store = storage.RawStore()
    store.clear("garmin")
    store.load("garmin", payloads.records(states, now=datetime.now(UTC)))
    save_goal(DEMO_GOAL.model_copy(update={"event_date": end + timedelta(weeks=8)}))
    return len(states), sum(len(s.activities) for s in states)


if __name__ == "__main__":
    main()
