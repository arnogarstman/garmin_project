import pytest

from garminreader import config


def test_demo_profile_ignores_prod_location_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """In demo mode, data locations come from DEMO_* settings or data/demo/, never from the prod settings.

    `synthesize` deletes and rewrites the demo raw data, so a prod setting such as DATABASE must
    never be able to point it at real data.
    """
    monkeypatch.setenv("DATA_PROFILE", "demo")
    for key in ("DATABASE", "GOAL_PATH"):
        monkeypatch.setenv(key, "md:real")
        monkeypatch.delenv(f"DEMO_{key}", raising=False)
    assert config.database() == str(config.PROJECT_ROOT / "data/demo/warehouse.duckdb")
    assert config.goal_path() == str(config.PROJECT_ROOT / "data/demo/goal.json")


def test_motherduck_and_urls_are_kept_as_is(monkeypatch: pytest.MonkeyPatch) -> None:
    """md:<name> and URLs are passed through untouched; only plain paths resolve against the project root."""
    monkeypatch.delenv("DATA_PROFILE", raising=False)
    monkeypatch.setenv("DATABASE", "md:garmin")
    monkeypatch.setenv("GOAL_PATH", "s3://bucket/goal.json")
    assert config.database() == "md:garmin"
    assert config.is_motherduck(config.database())
    assert config.goal_path() == "s3://bucket/goal.json"


def test_prod_is_the_default_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without DATA_PROFILE the real data is used, at its usual location."""
    monkeypatch.delenv("DATA_PROFILE", raising=False)
    monkeypatch.delenv("DATABASE", raising=False)
    assert not config.is_demo()
    assert config.database() == str(config.PROJECT_ROOT / "data/warehouse.duckdb")


def test_unknown_profile_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo in DATA_PROFILE fails loudly instead of silently falling back to real data."""
    monkeypatch.setenv("DATA_PROFILE", "staging")
    with pytest.raises(RuntimeError):
        config.data_profile()
