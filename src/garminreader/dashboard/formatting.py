"""Display formatting for times and paces, shared by the dashboard tabs."""

import math

MISSING = "–"


def duration(seconds: float | None) -> str:
    """Seconds as h:mm:ss, or m:ss under an hour: 5956 -> '1:39:16'."""
    if seconds is None or math.isnan(seconds):
        return MISSING
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def signed_duration(seconds: float | None) -> str:
    """A time difference with its sign: -95 -> '-1:35', 300 -> '+5:00'."""
    if seconds is None or math.isnan(seconds):
        return MISSING
    sign = "-" if seconds < 0 else "+"
    return f"{sign}{duration(abs(seconds))}"


def pace(min_per_km: float | None) -> str:
    """Minutes per km as m:ss /km: 4.69 -> '4:41 /km'."""
    if min_per_km is None or math.isnan(min_per_km):
        return MISSING
    return f"{duration(min_per_km * 60)} /km"
