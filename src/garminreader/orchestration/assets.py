"""The pipeline's assets: raw Garmin data (bronze), the dbt models (silver and
gold) and Claude's workout reviews, all in the configured database.

Raw is partitioned by day, so a backfill is "materialize these partitions" and
a failed day can be re-run on its own. Each partition fetches its day and the
day before, because Garmin keeps updating recent days after late watch syncs;
the raw store's change detection drops what did not change.
"""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import dagster as dg
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets
from dbt.cli.main import dbtRunner

from garminreader import config
from garminreader.ingest.sources.coach.source import CoachSource
from garminreader.ingest.sources.garmin.source import GarminSource
from garminreader.ingest.storage import RawStore
from garminreader.transform import configure_dbt_env

RAW_KEY = dg.AssetKey(["raw", "garmin"])
LOADS_KEY = dg.AssetKey(["raw", "garmin_loads"])
COACH_KEY = dg.AssetKey(["raw", "coach"])
TIMEZONE = "Europe/Amsterdam"

daily = dg.DailyPartitionsDefinition(start_date=config.history_start(), end_offset=1, timezone=TIMEZONE)


def _raw_specs(description: str, partitions_def: dg.PartitionsDefinition | None = None) -> list[dg.AssetSpec]:
    """One ingest step writes two assets: the records, and the run markers that commit them."""
    common = {"group_name": "ingest", "kinds": {"python", "json"}, "partitions_def": partitions_def}
    return [
        dg.AssetSpec(RAW_KEY, description=description, **common),  # type: ignore[arg-type]
        dg.AssetSpec(LOADS_KEY, description="Run log: one row per successful load.", **common),  # type: ignore[arg-type]
    ]


def _results(metadata: dict[str, Any]) -> Iterator[dg.MaterializeResult[None]]:
    yield dg.MaterializeResult(asset_key=RAW_KEY, metadata=metadata)
    yield dg.MaterializeResult(asset_key=LOADS_KEY)


@dg.multi_asset(
    name="garmin_raw",
    specs=_raw_specs("Raw Garmin Connect responses for one day (and the day before), in raw.payloads.", daily),
    retry_policy=dg.RetryPolicy(max_retries=2, delay=60, backoff=dg.Backoff.EXPONENTIAL),
)
def garmin_raw(context: dg.AssetExecutionContext) -> Iterator[dg.MaterializeResult[None]]:
    day = date.fromisoformat(context.partition_key)
    result = RawStore().load("garmin", GarminSource().extract(since=day - timedelta(days=1), until=day))
    yield from _results({"load_id": result.load_id, "fetched": result.fetched, "stored": result.inserted})


@dg.asset(
    key=COACH_KEY,
    group_name="coach",
    kinds={"python", "json"},
    # The marts the reviews read. dbt models the reviews in turn, so Dagster runs dbt in two
    # steps with this one in between.
    deps=[dg.AssetKey(["marts", name]) for name in ("fct_activities", "fct_daily_health", "fct_race_predictions")],
    description="Claude's review of each new workout, in raw.payloads (source coach).",
)
def workout_reviews() -> dg.MaterializeResult[None]:
    result = RawStore().load("coach", CoachSource().extract())
    return dg.MaterializeResult(metadata={"load_id": result.load_id, "reviewed": result.inserted})


configure_dbt_env()
dbt_project = DbtProject(
    project_dir=config.dbt_project_dir(),
    profiles_dir=config.dbt_project_dir(),
    target="local",
)


def _manifest_is_stale() -> bool:
    if not dbt_project.manifest_path.exists():
        return True
    built = dbt_project.manifest_path.stat().st_mtime
    sources = [*config.dbt_project_dir().glob("models/**/*"), *config.dbt_project_dir().glob("macros/**/*")]
    return any(f.stat().st_mtime > built for f in [*sources, config.dbt_project_dir() / "dbt_project.yml"])


if _manifest_is_stale():
    # dbt-core in process, not dagster-dbt's preparer: that one prefers a dbt Fusion (dbtf)
    # binary on PATH.
    parsed = dbtRunner().invoke(["parse", "--quiet", "--target", dbt_project.target or "local"])
    if not parsed.success:
        raise RuntimeError(f"dbt parse failed: {parsed.exception}")


@dbt_assets(manifest=dbt_project.manifest_path, project=dbt_project)
def dbt_models(context: dg.AssetExecutionContext, dbt: DbtCliResource):  # type: ignore[no-untyped-def]
    """Every dbt model, with its tests as asset checks."""
    yield from dbt.cli(["build"], context=context).stream()
