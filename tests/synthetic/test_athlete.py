from datetime import date

import pytest

from garminreader.synthetic import athlete

END = date(2026, 10, 8)


@pytest.mark.parametrize(
    ("distance_m", "expected_s"),
    [(5_000, 19 * 60 + 57), (athlete.HALF_MARATHON_M, 91 * 60 + 35), (athlete.MARATHON_M, 190 * 60 + 49)],
)
def test_race_times_match_daniels_tables(distance_m: float, expected_s: int) -> None:
    """VDOT 50 gives the race times in Jack Daniels' published tables, within 0.5%.

    Race predictions and race results in the demo are derived from this, so it anchors
    the realism of every time on the Races tab.
    """
    assert athlete.race_time_s(50, distance_m) == pytest.approx(expected_s, rel=0.005)


def test_same_seed_gives_the_same_athlete() -> None:
    """The simulation is reproducible: a seed and end date always produce identical data, another seed does not."""
    assert athlete.simulate(END, 120, seed=1) == athlete.simulate(END, 120, seed=1)
    assert athlete.simulate(END, 120, seed=1) != athlete.simulate(END, 120, seed=2)


def test_story_has_two_half_marathons_with_progress() -> None:
    """The demo year contains two half marathons, on Sundays, and the second is faster.

    This is what gives the Races tab a real progression to show.
    """
    states = athlete.simulate(END, 365, seed=42)
    races = [a for s in states for a in s.activities if a.kind == "race"]
    assert len(races) == 2
    assert all(r.day.weekday() == 6 for r in races)
    assert races[1].duration_s < races[0].duration_s


def test_no_training_while_ill() -> None:
    """During the simulated illness there are no activities, so recovery metrics dip without training to blame."""
    states = athlete.simulate(END, 365, seed=42)
    sick = [s for s in states if s.is_ill]
    assert sick and all(not s.activities for s in sick)


def test_zone_time_adds_up_to_the_activity_duration() -> None:
    """The time spread over the five heart rate zones equals the activity's duration."""
    zones = athlete._zones(140, 3_600)
    assert sum(zones) == pytest.approx(3_600, abs=0.01)
    assert max(range(5), key=lambda i: zones[i]) == 2  # 140 bpm lies in zone 3 (135-153)
