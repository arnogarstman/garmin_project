"""`uv run snapshot [--out PATH] [--days N]`: write the marts as a static HTML page."""

import argparse
import logging
from pathlib import Path

from garminreader import config, db
from garminreader.snapshot import data, render

logger = logging.getLogger("snapshot")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = config.PROJECT_ROOT / "data" / ("demo" if config.is_demo() else "") / "snapshot.html"
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--days", type=int, default=365, help="history shown in the charts")
    args = parser.parse_args()

    if not db.exists():
        parser.error(f"No database at {config.database()}; run `uv run transform` first")
    html = render.render(data.load(days=args.days))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%.0f kB) from %s", args.out, len(html) / 1e3, config.database())


if __name__ == "__main__":
    main()
