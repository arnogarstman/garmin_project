from pathlib import Path

import pytest

from garminreader import config


def test_demo_profile_ignores_prod_location_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """In demo mode, data locations come from DEMO_* settings or data/demo/, never from the prod settings.

    `synthesize` deletes and rewrites the demo raw data, so a prod setting such as RAW_ROOT must
    never be able to point it at real data.
    """
    monkeypatch.setenv("DATA_PROFILE", "demo")
    for key in ("DUCKDB_PATH", "RAW_ROOT", "GOAL_PATH", "WAREHOUSE_URL"):
        monkeypatch.setenv(key, "data/real")
        monkeypatch.delenv(f"DEMO_{key}", raising=False)
    assert config.duckdb_path() == config.PROJECT_ROOT / "data/demo/warehouse.duckdb"
    assert config.raw_root() == str(config.PROJECT_ROOT / "data/demo/raw")
    assert config.goal_path() == str(config.PROJECT_ROOT / "data/demo/goal.json")
    assert config.warehouse_url() is None


def test_object_storage_urls_are_kept_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """A URL such as abfs://raw is passed through untouched; only plain paths resolve against the project root."""
    monkeypatch.setenv("DATA_PROFILE", "demo")
    monkeypatch.setenv("DEMO_RAW_ROOT", "abfs://raw")
    assert config.raw_root() == "abfs://raw"


def test_prod_is_the_default_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without DATA_PROFILE the real data is used, at its usual location."""
    monkeypatch.delenv("DATA_PROFILE", raising=False)
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    assert not config.is_demo()
    assert config.duckdb_path() == config.PROJECT_ROOT / Path("data/warehouse.duckdb")


def test_unknown_profile_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in DATA_PROFILE fails loudly instead of silently falling back to real data."""
    monkeypatch.setenv("DATA_PROFILE", "staging")
    with pytest.raises(RuntimeError):
        config.data_profile()
