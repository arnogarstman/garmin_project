import importlib
from types import ModuleType

import dagster as dg
import pytest

from garminreader.orchestration import assets, definitions


def _load(monkeypatch: pytest.MonkeyPatch, profile: str) -> ModuleType:
    """The definitions module as loaded under a data profile (it picks its raw asset at import)."""
    monkeypatch.setenv("DATA_PROFILE", profile)
    return importlib.reload(definitions)


def _deps(defs: dg.Definitions, key: dg.AssetKey) -> set[dg.AssetKey]:
    spec = next(s for s in defs.resolve_all_asset_specs() if s.key == key)
    return {dep.asset_key for dep in spec.deps}


def test_raw_data_feeds_the_dbt_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dbt sources map to the garmin_raw asset, so lineage runs from ingest through every model.

    Without that mapping Dagster would show the dbt models as having no upstream, and
    a run could build them before the raw data was loaded.
    """
    defs = _load(monkeypatch, "prod").defs
    assert assets.RAW_KEY in _deps(defs, dg.AssetKey(["staging", "stg_garmin__sleep"]))
    keys = {s.key for s in defs.resolve_all_asset_specs()}
    assert {assets.RAW_KEY, dg.AssetKey(["marts", "fct_race_results"])} <= keys


def test_real_data_is_partitioned_by_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """With real data, raw ingest and the daily job are partitioned by day, so backfills and re-runs work per day."""
    module = _load(monkeypatch, "prod")
    job = module.defs.resolve_job_def(module.JOB_NAME)
    assert job.partitions_def == assets.daily
    assert module.raw_asset is assets.garmin_raw


def test_demo_uses_the_synthetic_raw_asset(monkeypatch: pytest.MonkeyPatch) -> None:
    """The demo swaps in the simulated athlete under the same asset key, unpartitioned, and never calls Garmin."""
    module = _load(monkeypatch, "demo")
    assert module.raw_asset is assets.synthetic_raw
    assert module.defs.resolve_job_def(module.JOB_NAME).partitions_def is None
    assert assets.RAW_KEY in _deps(module.defs, dg.AssetKey(["staging", "stg_garmin__sleep"]))
