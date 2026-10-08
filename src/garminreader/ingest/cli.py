"""Run a source: `uv run ingest <source> [--since YYYY-MM-DD]`."""

import argparse
import logging
from datetime import date

from garminreader import config
from garminreader.ingest import storage
from garminreader.ingest.sources import SOURCES

logger = logging.getLogger("ingest")


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingest")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument("--since", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    source = SOURCES[args.source]()
    with storage.connect(config.duckdb_path()) as con:
        storage.load(con, source.name, source.extract(since=args.since))


if __name__ == "__main__":
    main()
