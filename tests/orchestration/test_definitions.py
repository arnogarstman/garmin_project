import dagster as dg

from garminreader.orchestration import assets, definitions


def _deps(defs: dg.Definitions, key: dg.AssetKey) -> set[dg.AssetKey]:
    spec = next(s for s in defs.resolve_all_asset_specs() if s.key == key)
    return {dep.asset_key for dep in spec.deps}


def test_raw_data_feeds_the_dbt_models() -> None:
    """The dbt sources map to the garmin_raw asset, so lineage runs from ingest through every model.

    Without that mapping Dagster would show the dbt models as having no upstream, and
    a run could build them before the raw data was loaded.
    """
    defs = definitions.defs
    assert assets.RAW_KEY in _deps(defs, dg.AssetKey(["staging", "stg_garmin__sleep"]))
    keys = {s.key for s in defs.resolve_all_asset_specs()}
    assert {assets.RAW_KEY, dg.AssetKey(["marts", "fct_race_results"])} <= keys


def test_reviews_sit_between_the_marts_and_their_model() -> None:
    """The review step reads the marts and feeds the review model, so Dagster runs dbt around it."""
    defs = definitions.defs
    assert dg.AssetKey(["marts", "fct_activities"]) in _deps(defs, assets.COACH_KEY)
    assert assets.COACH_KEY in _deps(defs, dg.AssetKey(["staging", "stg_coach__workout_reviews"]))


def test_the_daily_job_is_partitioned_by_day() -> None:
    """Raw ingest and the daily job are partitioned by day, so backfills and re-runs work per day."""
    job = definitions.defs.resolve_job_def(definitions.JOB_NAME)
    assert job.partitions_def == assets.daily
