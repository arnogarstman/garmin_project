"""Dagster definitions for the active data profile.

Locally: `uv run dagster dev` for the UI (lineage, partitions, backfills,
check results). In the cloud a scheduled container runs the same job once
through `uv run pipeline`, without a long-lived Dagster instance.
"""

import sys
from pathlib import Path

import dagster as dg
from dagster_dbt import DbtCliResource

from garminreader.orchestration import assets, checks

JOB_NAME = "daily_refresh"
# dbt-core from this environment: dagster-dbt otherwise prefers a dbt Fusion (dbtf) binary on PATH.
DBT_EXECUTABLE = str(Path(sys.executable).parent / "dbt")

daily_refresh = dg.define_asset_job(
    JOB_NAME,
    selection=dg.AssetSelection.all(),
    # Partitioned by day: inferred from the raw asset.
    description="Ingest, build every dbt model and its tests, and run the checks.",
)

# The latest partition, which is today since the partitions end one day ahead.
schedule = dg.build_schedule_from_partitioned_job(daily_refresh, hour_of_day=6, minute_of_hour=0)

defs = dg.Definitions(
    assets=[assets.garmin_raw, assets.workout_reviews, assets.dbt_models],
    asset_checks=[checks.raw_is_fresh, checks.garmin_signals_are_fresh],
    jobs=[daily_refresh],
    schedules=[schedule],
    resources={"dbt": DbtCliResource(project_dir=assets.dbt_project, dbt_executable=DBT_EXECUTABLE)},
)
