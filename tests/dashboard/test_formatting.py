import math

from garminreader.dashboard import formatting


def test_duration_switches_to_hours_from_one_hour() -> None:
    """Race times read like a race clock: m:ss below an hour, h:mm:ss from an hour, rounded to seconds."""
    assert formatting.duration(1175) == "19:35"
    assert formatting.duration(5956.4) == "1:39:16"
    assert formatting.duration(3600) == "1:00:00"


def test_signed_duration_shows_direction() -> None:
    """Differences carry an explicit sign, so a time gained or lost is visible at a glance."""
    assert formatting.signed_duration(-95) == "-1:35"
    assert formatting.signed_duration(300) == "+5:00"


def test_pace_is_minutes_and_seconds_per_km() -> None:
    """Decimal minutes per km become m:ss /km: 4.69 min is 4 minutes 41 seconds."""
    assert formatting.pace(4.69) == "4:41 /km"


def test_missing_values_render_as_placeholder() -> None:
    """None and NaN (how pandas represents missing numbers) show the placeholder instead of raising."""
    for fn in (formatting.duration, formatting.signed_duration, formatting.pace):
        assert fn(None) == formatting.MISSING
        assert fn(math.nan) == formatting.MISSING
