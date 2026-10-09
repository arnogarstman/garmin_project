"""A simulated recreational runner, day by day, with cause and effect between
training, fitness, recovery and body weight, so the demo data tells the same
kind of story real data does.

The story, scaled to the number of days simulated: a periodised plan (three
build weeks, one recovery week) with volume rising over the year, a half
marathon at 30% and again at 85% of the period (tapered, faster the second
time), a week of illness halfway, steady weight loss, and easy runs that are
too hard at first and drift into zone 2 as the year goes on.

Fitness follows the classic impulse-response model: chronic load (fitness)
and acute load (fatigue) are exponentially weighted averages of daily
training load. VO2 max rises with chronic load and, being per kg, with weight
loss; race times follow from VO2 max via Jack Daniels' VDOT formulas.
Everything is driven by one seeded random generator, so a seed and an end
date always produce the same athlete.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

HEIGHT_M = 1.84
MAX_HR = 192
HR_ZONE_FLOORS = (97, 116, 135, 154, 174)
ACUTE_DAYS = 7
CHRONIC_DAYS = 28
HALF_MARATHON_M = 21_097.5
MARATHON_M = 42_195.0

# Run type -> (share of weekly distance, pace factor vs half marathon pace, load per minute,
#              aerobic effect, anaerobic effect, average HR)
RUN_TYPES: dict[str, tuple[float, float, float, float, float, int]] = {
    "intervals": (0.20, 1.08, 3.0, 3.8, 2.6, 158),
    "easy": (0.225, 1.25, 1.4, 2.7, 0.2, 127),
    "long": (0.35, 1.20, 1.7, 3.6, 0.4, 131),
    "race": (0.0, 1.00, 3.6, 4.9, 1.6, 173),
}
# Weekday -> session. Monday is 0.
WEEK_PLAN = {1: "intervals", 3: "easy", 5: "easy", 6: "long"}


@dataclass(frozen=True)
class Activity:
    activity_id: int
    day: date
    start_hour: float
    kind: str  # run type, "strength" or "cycling"
    distance_m: float
    duration_s: float
    avg_hr: int
    max_hr: int
    training_load: float
    aerobic_effect: float
    anaerobic_effect: float
    zone_seconds: tuple[float, float, float, float, float]
    elevation_gain_m: float
    calories: float


@dataclass
class DayState:
    day: date
    weight_kg: float | None
    weigh_ins: list[float]
    body_fat_pct: float
    muscle_mass_kg: float
    body_water_pct: float
    vo2max: float
    acute_load: float
    chronic_load: float
    resting_hr: int
    hrv: int
    hrv_weekly_avg: int | None
    hrv_baseline: tuple[int, int] | None
    sleep_s: int
    sleep_score: int
    sleep_start_utc_hour: float
    avg_stress: int
    body_battery_high: int
    body_battery_low: int
    readiness: int
    steps: int
    predicted_s: dict[str, int]
    is_ill: bool
    status_phrase: str
    activities: list[Activity] = field(default_factory=list)


@dataclass(frozen=True)
class Story:
    """Key days of the simulated year, as offsets from the first day."""

    races: tuple[int, ...]
    illness: range


def story(days: int, start: date) -> Story:
    def sunday_near(offset: int) -> int:
        weekday = (start + timedelta(days=offset)).weekday()
        return offset + (6 - weekday)

    races = tuple(d for d in (sunday_near(int(days * 0.30)), sunday_near(int(days * 0.85))) if d < days)
    sick_from = int(days * 0.55)
    return Story(races=races, illness=range(sick_from, sick_from + 8))


def simulate(end: date, days: int, seed: int) -> list[DayState]:
    rng = random.Random(seed)
    start = end - timedelta(days=days - 1)
    plot = story(days, start)
    acute, chronic = 25.0, 30.0
    hrv_history: list[int] = []
    longest_runs: list[tuple[int, float]] = []
    vo2_last = 47.0
    next_id = 10_000_000_000
    states: list[DayState] = []

    for offset in range(days):
        day = start + timedelta(days=offset)
        progress = offset / max(days - 1, 1)
        ill = offset in plot.illness
        weight = 87.0 - 6.5 * progress + 0.6 * math.sin(progress * 9) + rng.gauss(0, 0.35)

        activities: list[Activity] = []
        if not ill:
            for kind in _sessions_for(day, offset, plot, rng):
                activity = _activity(next_id, day, kind, offset, plot, progress, vo2_last, weight, acute, chronic, rng)
                activities.append(activity)
                next_id += 1
        daily_load = sum(a.training_load for a in activities)
        acute += (daily_load - acute) / ACUTE_DAYS
        chronic += (daily_load - chronic) / CHRONIC_DAYS
        strain = acute - chronic

        vo2_rel = (37.0 + 0.11 * chronic) * 86.0 / weight
        if any(a.kind in RUN_TYPES for a in activities):
            vo2_last = round(vo2_rel + rng.gauss(0, 0.2), 1)
        longest_runs += [(offset, a.distance_m) for a in activities if a.kind in RUN_TYPES]
        recent_longest = max((d for o, d in longest_runs if offset - o < 28), default=0.0) / 1000

        resting_hr = round(56 - 0.08 * chronic + 0.12 * strain + rng.gauss(0, 1.0) + (6 if ill else 0))
        hrv = round(46 + 0.2 * chronic - 0.25 * strain + rng.gauss(0, 4) - (22 if ill else 0))
        hrv_history.append(hrv)
        hrv_weekly = round(sum(hrv_history[-7:]) / 7) if len(hrv_history) >= 7 else None
        baseline = None
        if len(hrv_history) >= 21:
            mean = sum(hrv_history[-21:]) / 21
            baseline = (round(mean - 6), round(mean + 6))

        hard_yesterday = bool(states) and any(a.kind in ("intervals", "race") for a in states[-1].activities)
        sleep_h = 7.2 + rng.gauss(0, 0.55) - (0.3 if hard_yesterday else 0) + (0.6 if ill else 0)
        stress = _clamp(round(28 + 0.3 * strain + rng.gauss(0, 5) + (15 if ill else 0)), 5, 95)
        sleep_score = _clamp(round(38 + 6.5 * sleep_h - 0.15 * stress + rng.gauss(0, 4)), 20, 100)
        bb_high = _clamp(round(30 + 0.65 * sleep_score - 0.3 * stress + rng.gauss(0, 5)), 15, 100)
        bb_low = _clamp(round(bb_high - 45 - daily_load / 6 + rng.gauss(0, 6)), 5, bb_high - 5)
        hrv_gap = hrv - (baseline[0] + 6 if baseline else hrv)
        readiness = _clamp(
            round(66 + 1.5 * hrv_gap + 0.6 * (sleep_score - 75) - 0.8 * strain + rng.gauss(0, 6)), 1, 100
        )

        steps = round(8_500 + rng.gauss(0, 2_200) + sum(a.distance_m for a in activities) * 1.3)
        states.append(
            DayState(
                day=day,
                weight_kg=round(weight, 2),
                weigh_ins=_weigh_ins(weight, rng),
                body_fat_pct=round(23.5 - 4.0 * progress + rng.gauss(0, 0.6), 1),
                muscle_mass_kg=round(35.0 + 0.6 * progress + rng.gauss(0, 0.25), 2),
                body_water_pct=round(55.8 + 2.2 * progress + rng.gauss(0, 0.4), 1),
                vo2max=vo2_last,
                acute_load=round(acute),
                chronic_load=round(chronic),
                resting_hr=resting_hr,
                hrv=hrv,
                hrv_weekly_avg=hrv_weekly,
                hrv_baseline=baseline,
                sleep_s=round(sleep_h * 3600),
                sleep_score=sleep_score,
                sleep_start_utc_hour=21.5 + rng.gauss(0, 0.4),
                avg_stress=stress,
                body_battery_high=bb_high,
                body_battery_low=bb_low,
                readiness=readiness,
                steps=max(steps, 1_500),
                predicted_s=_predictions(vo2_last, recent_longest),
                is_ill=ill,
                status_phrase=_status_phrase(offset, plot, acute, chronic, states),
                activities=activities,
            )
        )
    return states


def race_time_s(vdot: float, distance_m: float) -> float:
    """The time a runner with this VDOT can race the distance in (Daniels' formulas, solved by bisection)."""

    def vdot_for(minutes: float) -> float:
        speed = distance_m / minutes
        vo2 = -4.60 + 0.182258 * speed + 0.000104 * speed**2
        fraction = 0.8 + 0.1894393 * math.exp(-0.012778 * minutes) + 0.2989558 * math.exp(-0.1932605 * minutes)
        return vo2 / fraction

    low, high = 5.0, 600.0
    for _ in range(60):
        mid = (low + high) / 2
        if vdot_for(mid) > vdot:
            low = mid
        else:
            high = mid
    return (low + high) / 2 * 60


def _sessions_for(day: date, offset: int, plot: Story, rng: random.Random) -> list[str]:
    if offset in plot.races:
        return ["race"]
    if any(0 < race - offset <= 2 for race in plot.races):
        return []  # rest before a race
    sessions = []
    planned = WEEK_PLAN.get(day.weekday())
    if planned and rng.random() > 0.08:
        sessions.append(planned)
    if day.weekday() == 2 and rng.random() < 0.5:
        sessions.append("strength")
    if day.weekday() == 5 and rng.random() < 0.25:
        sessions = ["cycling"]
    return sessions


def _week_km(offset: int, plot: Story, progress: float) -> float:
    base = 22 + 26 * progress
    block = (1.0, 1.1, 1.2, 0.7)[(offset // 7) % 4]
    for race in plot.races:
        if 0 < race - offset <= 7:
            return base * 0.6  # taper
        if 0 <= offset - race < 7:
            return base * 0.5  # recovery after the race
    return base * block


def _activity(
    activity_id: int,
    day: date,
    kind: str,
    offset: int,
    plot: Story,
    progress: float,
    vo2max: float,
    weight: float,
    acute: float,
    chronic: float,
    rng: random.Random,
) -> Activity:
    fatigue_hr = max(0.0, acute - chronic) * 0.08
    if kind in ("strength", "cycling"):
        minutes = rng.uniform(40, 55) if kind == "strength" else rng.uniform(60, 100)
        avg_hr = round((112 if kind == "strength" else 132) + rng.gauss(0, 4) + fatigue_hr)
        distance = 0.0 if kind == "strength" else minutes / 60 * rng.uniform(24, 28) * 1000
        load = minutes * (0.7 if kind == "strength" else 1.1)
        return Activity(
            activity_id=activity_id,
            day=day,
            start_hour=18.5 if kind == "strength" else 10.0,
            kind=kind,
            distance_m=round(distance),
            duration_s=round(minutes * 60),
            avg_hr=avg_hr,
            max_hr=avg_hr + 25,
            training_load=round(load),
            aerobic_effect=1.8 if kind == "strength" else 2.9,
            anaerobic_effect=0.3,
            zone_seconds=_zones(avg_hr, minutes * 60),
            elevation_gain_m=0.0,
            calories=round(minutes * (7 if kind == "strength" else 10)),
        )

    share, pace_factor, load_per_min, aerobic, anaerobic, base_hr = RUN_TYPES[kind]
    half_pace_s_per_km = race_time_s(vo2max, HALF_MARATHON_M) / (HALF_MARATHON_M / 1000)
    if kind == "race":
        distance = HALF_MARATHON_M * rng.uniform(1.004, 1.015)  # GPS measures a little long
        pace = half_pace_s_per_km * rng.uniform(0.995, 1.015)
    else:
        distance = max(4_000.0, _week_km(offset, plot, progress) * share * 1000 * rng.uniform(0.9, 1.1))
        pace = half_pace_s_per_km * pace_factor * rng.uniform(0.97, 1.03)
    duration = distance / 1000 * pace
    # Easy running starts out too hard (zone 3) and settles into zone 2 as the year goes on.
    drift = 12 * (1 - progress) if kind in ("easy", "long") else 0
    avg_hr = round(base_hr + drift + rng.gauss(0, 3) + fatigue_hr)
    return Activity(
        activity_id=activity_id,
        day=day,
        start_hour=8.5 if kind in ("long", "race") else 18.0,
        kind=kind,
        distance_m=round(distance, 1),
        duration_s=round(duration, 1),
        avg_hr=avg_hr,
        max_hr=min(MAX_HR, avg_hr + rng.randint(10, 18)),
        training_load=round(duration / 60 * load_per_min),
        aerobic_effect=round(min(5.0, aerobic + rng.gauss(0, 0.2)), 1),
        anaerobic_effect=round(max(0.0, anaerobic + rng.gauss(0, 0.2)), 1),
        zone_seconds=_zones(avg_hr, duration),
        elevation_gain_m=round(distance / 1000 * rng.uniform(3, 9)),
        calories=round(distance / 1000 * weight * 1.0),
    )


def _zones(avg_hr: int, seconds: float) -> tuple[float, float, float, float, float]:
    """Spread the activity's time over the HR zones, assuming heart rate is normally
    distributed around its average (sd 8 bpm); time below zone 1 counts as zone 1."""

    def below(bpm: float) -> float:
        return 0.5 * (1 + math.erf((bpm - avg_hr) / (8 * math.sqrt(2))))

    edges = [*HR_ZONE_FLOORS[1:], math.inf]
    shares = [below(edges[0])] + [below(edges[i + 1]) - below(edges[i]) for i in range(4)]
    zones = [round(seconds * share, 3) for share in shares]
    return (zones[0], zones[1], zones[2], zones[3], zones[4])


def _weigh_ins(weight: float, rng: random.Random) -> list[float]:
    if rng.random() > 0.75:
        return []
    readings = [weight]
    if rng.random() < 0.2:
        readings.append(weight + rng.gauss(0.3, 0.2))
    return [round(r, 2) for r in readings]


def _predictions(vo2max: float, longest_run_km: float) -> dict[str, int]:
    """Garmin-style predictions: VDOT race times, slower for long races without the long runs to back them."""
    half_penalty = 1 + max(0.0, 16 - longest_run_km) * 0.004
    full_penalty = 1 + max(0.0, 30 - longest_run_km) * 0.004
    return {
        "time5K": round(race_time_s(vo2max, 5_000)),
        "time10K": round(race_time_s(vo2max, 10_000)),
        "timeHalfMarathon": round(race_time_s(vo2max, HALF_MARATHON_M) * half_penalty),
        "timeMarathon": round(race_time_s(vo2max, MARATHON_M) * full_penalty),
    }


def _status_phrase(offset: int, plot: Story, acute: float, chronic: float, history: list[DayState]) -> str:
    if offset < 14:
        return "NO_STATUS_1"
    ratio = acute / chronic if chronic else 1.0
    if any(0 <= race - offset <= 7 for race in plot.races):
        return "PEAKING_1"
    if offset in plot.illness or ratio < 0.7:
        return "RECOVERY_1"
    if ratio > 1.4:
        return "UNPRODUCTIVE_1"
    vo2_trend = history[-1].vo2max - history[-14].vo2max
    return "PRODUCTIVE_1" if vo2_trend > 0.2 else "MAINTAINING_1"


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
