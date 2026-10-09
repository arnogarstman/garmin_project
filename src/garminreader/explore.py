"""Browse the warehouse in the DuckDB UI: `uv run explore`.

The session itself is in-memory and the warehouse is attached read-only: the
UI keeps its own state in an internal database it must be able to write, so
opening the whole session read-only breaks it. UI cells run in their own
sessions, which start in the in-memory database and do not inherit USE, so
every warehouse table is mirrored there as a view: `from marts.fct_daily_health`
then works in any cell.

The UI reads a snapshot copy taken at startup, not the live file, so it never
holds a lock on the warehouse: ingest, transform and the dashboard keep
working while it runs. Restart it to see newer data.
"""

import logging
import shutil
import tempfile
import threading
from pathlib import Path

import duckdb

from garminreader import config

logger = logging.getLogger("explore")


def _mirror_as_views(con: duckdb.DuckDBPyConnection, catalog: str) -> None:
    """Create memory.<schema>.<name> views over every table and view in catalog."""
    relations = con.execute(
        """
        select schema_name, table_name from duckdb_tables() where database_name = $1
        union all
        select schema_name, view_name from duckdb_views() where database_name = $1 and not internal
        """,
        [catalog],
    ).fetchall()
    for schema, name in relations:
        con.execute(f'CREATE SCHEMA IF NOT EXISTS memory."{schema}"')
        con.execute(f'CREATE VIEW memory."{schema}"."{name}" AS SELECT * FROM {catalog}."{schema}"."{name}"')
    logger.info("Mirrored %d warehouse tables and views", len(relations))


def _snapshot(path: Path, directory: Path) -> Path:
    """Copy the warehouse (and its WAL, if a write is pending) into directory."""
    target = directory / path.name
    shutil.copy2(path, target)
    wal = path.with_name(path.name + ".wal")
    if wal.exists():
        shutil.copy2(wal, directory / wal.name)
    return target


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    database = config.database()
    if config.is_motherduck(database):
        raise SystemExit(f"{database} is in MotherDuck; explore it in the MotherDuck web UI instead")
    path = Path(database)
    if not path.exists():
        raise SystemExit(f"No warehouse at {path}; run `uv run ingest garmin && uv run transform` first")

    with tempfile.TemporaryDirectory(prefix="garminreader-explore-") as tmp:
        snapshot = _snapshot(path, Path(tmp))
        con = duckdb.connect()
        con.execute(f"ATTACH '{snapshot}' AS warehouse (READ_ONLY)")
        _mirror_as_views(con, "warehouse")
        con.execute("CALL start_ui()")
        logger.info("DuckDB UI running at http://localhost:4213 on a snapshot of %s; Ctrl+C to stop", path)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            logger.info("Stopping")
        finally:
            con.close()


if __name__ == "__main__":
    main()
