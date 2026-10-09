"""`uv run snapshot [--out PATH] [--days N] [--live]`: write the marts as a static HTML page.

With --live the page embeds no data: it queries the configured MotherDuck database
through the viewer's MotherDuck connector each time it is opened (as a claude.ai
artifact declaring that connector)."""

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
    parser.add_argument("--live", action="store_true", help="query MotherDuck when opened instead of embedding data")
    args = parser.parse_args()

    database = config.database()
    if args.live:
        if not config.is_motherduck(database):
            parser.error(f"--live needs a MotherDuck DATABASE (md:<name>), not {database}")
        html = render.render_live(database.removeprefix("md:"), data.live_sql(days=args.days), data.context())
    elif not db.exists():
        parser.error(f"No database at {database}; run `uv run transform` first")
    else:
        html = render.render(data.load(days=args.days))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    logger.info("Wrote %s (%.0f kB)%s from %s", args.out, len(html) / 1e3, " live" if args.live else "", database)


if __name__ == "__main__":
    main()
