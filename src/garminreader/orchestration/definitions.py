"""Dagster definitions for the active data profile.

Locally: `uv run dagster dev` for the UI (lineage, partitions, backfills,
check results). In the cloud a scheduled container runs the same job once
through `uv run pipeline`, without a long-lived Dagster instance.
"""

import sys
from pathlib import Path

import dagster as dg
from dagster_dbt import DbtCliResource

from garminreader import config
from garminreader.orchestration import assets, checks

JOB_NAME = "daily_refresh"
# dbt-core from this environment: dagster-dbt otherwise prefers a dbt Fusion (dbtf) binary on PATH.
DBT_EXECUTABLE = str(Path(sys.executable).parent / "dbt")

raw_asset = assets.synthetic_raw if config.is_demo() else assets.garmin_raw
daily_refresh = dg.define_asset_job(
    JOB_NAME,
    selection=dg.AssetSelection.all(),
    # Partitioned by day with real data: inferred from the raw asset.
    description="Ingest, build every dbt model and its tests, run the checks, and publish the warehouse.",
)

# Real data: the latest partition, which is today since the partitions end one day ahead.
schedule = (
    dg.ScheduleDefinition(job=daily_refresh, cron_schedule="0 6 * * *", execution_timezone=assets.TIMEZONE)
    if config.is_demo()
    else dg.build_schedule_from_partitioned_job(daily_refresh, hour_of_day=6, minute_of_hour=0)
)

defs = dg.Definitions(
    assets=[raw_asset, assets.dbt_models, assets.published_warehouse],
    asset_checks=[checks.raw_is_fresh, checks.garmin_signals_are_fresh],
    jobs=[daily_refresh],
    schedules=[schedule],
    resources={"dbt": DbtCliResource(project_dir=assets.dbt_project, dbt_executable=DBT_EXECUTABLE)},
)
