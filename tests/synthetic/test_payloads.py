from datetime import UTC, date, datetime

from garminreader.ingest.sources.garmin.source import DAY_ENDPOINTS, SNAPSHOT_ENDPOINTS
from garminreader.synthetic import athlete, payloads

STATES = athlete.simulate(date(2026, 10, 8), 90, seed=7)
RECORDS = list(payloads.records(STATES, now=datetime(2026, 10, 8, 12, tzinfo=UTC)))


def test_same_endpoints_as_the_real_garmin_source() -> None:
    """The demo produces exactly the endpoints the real Garmin source does, nothing more or less.

    This is the contract that lets the demo run the real dbt project unchanged: when an
    endpoint is added to the Garmin source, this fails until the generator covers it too.
    """
    assert {r.endpoint for r in RECORDS} == {*DAY_ENDPOINTS, *SNAPSHOT_ENDPOINTS, "activity"}


def test_records_are_keyed_like_the_real_source() -> None:
    """Per-day endpoints carry {"date"} once per day, activities a unique {"activity_id"}, snapshots no params.

    The loader's change detection and the staging models' "newest load wins" both rely on these keys.
    """
    days = {s.day.isoformat() for s in STATES}
    for endpoint in DAY_ENDPOINTS:
        dates = [r.params["date"] for r in RECORDS if r.endpoint == endpoint]
        assert sorted(dates) == sorted(days)
    activity_ids = [r.params["activity_id"] for r in RECORDS if r.endpoint == "activity"]
    assert len(activity_ids) == len(set(activity_ids)) > 0
    assert all(r.params == {} for r in RECORDS if r.endpoint in SNAPSHOT_ENDPOINTS)


def test_payloads_hold_nothing_personal() -> None:
    """No payload contains fields the real API uses for personal details (names, GPS, locations)."""
    personal = ("ownerFullName", "ownerDisplayName", "startLatitude", "locationName", "ownerProfileImageUrl")
    text = str([r.payload for r in RECORDS])
    assert not any(field in text for field in personal)
