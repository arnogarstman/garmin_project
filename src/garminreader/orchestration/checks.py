"""Health checks beyond the dbt tests (which Dagster already runs as asset
checks): is ingest keeping up, and is the watch still syncing to Garmin?
Both read stored state, so they mean the same in a local Dagster UI and in a
one-off cloud run without a long-lived Dagster instance."""

from datetime import UTC, datetime, timedelta

import dagster as dg
import duckdb

from garminreader import config
from garminreader.ingest.storage import RawStore
from garminreader.orchestration.assets import RAW_KEY

MAX_INGEST_AGE = timedelta(hours=26)  # a daily run, plus slack for a slow one


@dg.asset_check(asset=RAW_KEY, description=f"The last successful ingest is less than {MAX_INGEST_AGE} old.")
def raw_is_fresh() -> dg.AssetCheckResult:
    last = RawStore.from_url(config.raw_root()).last_loaded_at("garmin")
    age = datetime.now(UTC) - last if last else None
    return dg.AssetCheckResult(
        passed=age is not None and age < MAX_INGEST_AGE,
        metadata={"last_loaded_at": last.isoformat() if last else "never", "age_hours": _hours(age)},
    )


@dg.asset_check(
    asset=dg.AssetKey(["marts", "rpt_garmin_freshness"]),
    description="No freshness signal is stale: the watch uploads, sleep and daily summaries keep arriving.",
)
def garmin_signals_are_fresh() -> dg.AssetCheckResult:
    with duckdb.connect(str(config.duckdb_path()), read_only=True) as con:
        stale = [
            row[0] for row in con.execute("select signal from marts.rpt_garmin_freshness where is_stale").fetchall()
        ]
    return dg.AssetCheckResult(
        passed=not stale,
        severity=dg.AssetCheckSeverity.WARN,  # usually the watch not synced yet, not a pipeline fault
        metadata={"stale_signals": ", ".join(stale) or "none"},
    )


def _hours(age: timedelta | None) -> float:
    return round(age.total_seconds() / 3600, 1) if age else -1.0
