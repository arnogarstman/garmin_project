import pytest

from garminreader import config


def test_motherduck_and_urls_are_kept_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """md:<name> and URLs are passed through untouched; only plain paths resolve against the project root."""
    monkeypatch.setenv("DATABASE", "md:garmin")
    monkeypatch.setenv("GOAL_PATH", "s3://bucket/goal.json")
    assert config.database() == "md:garmin"
    assert config.is_motherduck(config.database())
    assert config.goal_path() == "s3://bucket/goal.json"


def test_default_locations_are_under_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without settings the database and goal file live in data/, which is gitignored."""
    monkeypatch.delenv("DATABASE", raising=False)
    monkeypatch.delenv("GOAL_PATH", raising=False)
    assert config.database() == str(config.PROJECT_ROOT / "data/warehouse.duckdb")
    assert config.goal_path() == str(config.PROJECT_ROOT / "data/goal.json")


def test_relative_paths_resolve_against_the_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE", "elsewhere/w.duckdb")
    assert config.database() == str(config.PROJECT_ROOT / "elsewhere/w.duckdb")
