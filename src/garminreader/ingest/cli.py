"""Run a source: `uv run ingest <source> [--since YYYY-MM-DD]`.

Without --since, a source resumes from its last successful load, minus a
short overlap because recent days keep changing upstream (late watch syncs).
A source that has never loaded uses its own default lookback.
"""

import argparse
import logging
from datetime import date, timedelta

from garminreader import config
from garminreader.ingest import storage
from garminreader.ingest.sources import SOURCES

logger = logging.getLogger("ingest")

REFETCH_DAYS = 1


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--since", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if config.is_demo():
        # The demo warehouse is meant to be published; real data must never land in it.
        parser.error("DATA_PROFILE=demo holds synthetic data only; use `uv run synthesize` instead")

    source = SOURCES[args.source]()
    since: date | None = args.since
    store = storage.RawStore()
    if since is None:
        last = store.last_loaded_at(source.name)
        since = last.date() - timedelta(days=REFETCH_DAYS) if last else None
        logger.info("No --since given; resuming %s from %s", source.name, since or "its default lookback")

    store.load(source.name, source.extract(since=since))


if __name__ == "__main__":
    main()
