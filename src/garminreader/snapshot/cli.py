"""`uv run snapshot [--out PATH] [--days N]`: write the marts as a static HTML page."""

import argparse
import logging
from pathlib import Path

from garminreader import config
from garminreader.snapshot import data, render

logger = logging.getLogger("snapshot")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=config.duckdb_path().parent / "snapshot.html")
    parser.add_argument("--days", type=int, default=365, help="history shown in the charts")
    args = parser.parse_args()

    warehouse = config.duckdb_path()
    if not warehouse.exists():
        parser.error(f"No warehouse at {warehouse}; run `uv run transform` first")
    html = render.render(data.load(warehouse, days=args.days))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%.0f kB) from %s", args.out, len(html) / 1e3, warehouse)


if __name__ == "__main__":
    main()
