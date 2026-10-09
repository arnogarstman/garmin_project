"""Render the simulated athlete as raw records shaped like Garmin Connect's
API responses, with the same endpoint names and request params the real
Garmin source uses. Downstream (loader, dbt, dashboard) cannot tell the
difference, which is the point: the demo exercises the real pipeline.

Payloads carry the fields the staging models read plus a few neighbours for
realism, not Garmin's full responses. No field holds anything personal."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from garminreader.ingest.sources.base import RawRecord
from garminreader.synthetic.athlete import HEIGHT_M, HR_ZONE_FLOORS, MAX_HR, Activity, DayState

DEVICE_ID = "1000000001"
DEVICE_NAME = "Forerunner 265"
USER_ID = 1

ACTIVITY_TYPES = {"strength": "strength_training", "cycling": "cycling"}
ACTIVITY_NAMES = {
    "easy": "Easy Run",
    "long": "Long Run",
    "intervals": "Intervals",
    "race": "Demo City Half Marathon",
    "strength": "Strength",
    "cycling": "Cycling",
}
READINESS_FEEDBACK = {
    "PRIME": "READY_FOR_ACTION",
    "HIGH": "WELL_RECOVERED",
    "MODERATE": "LISTEN_TO_YOUR_BODY",
    "LOW": "RECOVERY_IN_PROGRESS",
    "POOR": "TAKE_IT_EASY",
}
STATUS_CODES = {
    "NO_STATUS": 0,
    "DETRAINING": 2,
    "RECOVERY": 3,
    "MAINTAINING": 4,
    "UNPRODUCTIVE": 5,
    "PEAKING": 6,
    "PRODUCTIVE": 7,
}


def records(states: list[DayState], now: datetime) -> Iterator[RawRecord]:
    """All records for a simulated period, in the order the real source yields them."""
    yield RawRecord("device_last_used", _device(now), {})
    yield RawRecord("heart_rate_zones", _heart_rate_zones(), {})
    for state in states:
        for activity in state.activities:
            yield RawRecord("activity", _activity(activity), {"activity_id": activity.activity_id})
    for state in states:
        params = {"date": state.day.isoformat()}
        yield RawRecord("daily_summary", _daily_summary(state, now), params)
        yield RawRecord("sleep", _sleep(state), params)
        yield RawRecord("hrv", _hrv(state), params)
        yield RawRecord("training_readiness", _readiness(state), params)
        yield RawRecord("training_status", _training_status(state), params)
        yield RawRecord("weigh_ins", _weigh_ins(state), params)
        yield RawRecord("race_predictions", _race_predictions(state), params)


def _device(now: datetime) -> dict[str, Any]:
    return {"lastUsedDeviceName": DEVICE_NAME, "lastUsedDeviceUploadTime": _ms(now - timedelta(minutes=20))}


def _heart_rate_zones() -> list[dict[str, Any]]:
    floors = {f"zone{i + 1}Floor": floor for i, floor in enumerate(HR_ZONE_FLOORS)}
    return [
        {
            "trainingMethod": "HR_MAX",
            "sport": "DEFAULT",
            "maxHeartRateUsed": MAX_HR,
            "restingHeartRateUsed": None,
            "lactateThresholdHeartRateUsed": 172,
            **floors,
        }
    ]


def _activity(a: Activity) -> dict[str, Any]:
    start_local = datetime.combine(a.day, datetime.min.time()) + timedelta(hours=a.start_hour)
    start_utc = start_local - timedelta(hours=2)
    zones = {f"hrTimeInZone_{i + 1}": seconds for i, seconds in enumerate(a.zone_seconds)}
    return {
        "activityId": a.activity_id,
        "activityName": ACTIVITY_NAMES[a.kind],
        "activityType": {"typeKey": ACTIVITY_TYPES.get(a.kind, "running")},
        "eventType": {"typeKey": "race" if a.kind == "race" else "uncategorized"},
        "startTimeLocal": start_local.strftime("%Y-%m-%d %H:%M:%S"),
        "startTimeGMT": start_utc.strftime("%Y-%m-%d %H:%M:%S"),
        "distance": a.distance_m,
        "duration": a.duration_s,
        "movingDuration": round(a.duration_s * 0.99, 1),
        "averageHR": a.avg_hr,
        "maxHR": a.max_hr,
        "calories": a.calories,
        "elevationGain": a.elevation_gain_m,
        "aerobicTrainingEffect": a.aerobic_effect,
        "anaerobicTrainingEffect": a.anaerobic_effect,
        "activityTrainingLoad": a.training_load,
        **zones,
    }


def _daily_summary(s: DayState, now: datetime) -> dict[str, Any]:
    synced = min(now, datetime.combine(s.day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=21))
    return {
        "calendarDate": s.day.isoformat(),
        "restingHeartRate": s.resting_hr,
        "totalSteps": s.steps,
        "totalKilocalories": 2_350 + sum(a.calories for a in s.activities),
        "averageStressLevel": s.avg_stress,
        "bodyBatteryChargedValue": s.body_battery_high - s.body_battery_low + 10,
        "bodyBatteryDrainedValue": s.body_battery_high - s.body_battery_low,
        "bodyBatteryHighestValue": s.body_battery_high,
        "bodyBatteryLowestValue": s.body_battery_low,
        "bodyBatteryMostRecentValue": s.body_battery_low + 10,
        "sleepingSeconds": s.sleep_s,
        "lastSyncTimestampGMT": synced.strftime("%Y-%m-%dT%H:%M:%S.000"),
    }


def _sleep(s: DayState) -> dict[str, Any]:
    # The night ending on this day starts the evening before.
    start = datetime.combine(s.day - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    start += timedelta(hours=s.sleep_start_utc_hour)
    awake = round(s.sleep_s * 0.05)
    qualifier = "EXCELLENT" if s.sleep_score >= 90 else "GOOD" if s.sleep_score >= 80 else "FAIR"
    if s.sleep_score < 60:
        qualifier = "POOR"
    return {
        "dailySleepDTO": {
            "calendarDate": s.day.isoformat(),
            "sleepTimeSeconds": s.sleep_s,
            "deepSleepSeconds": round(s.sleep_s * 0.17),
            "remSleepSeconds": round(s.sleep_s * 0.22),
            "lightSleepSeconds": s.sleep_s - round(s.sleep_s * 0.17) - round(s.sleep_s * 0.22),
            "awakeSleepSeconds": awake,
            "sleepStartTimestampGMT": _ms(start),
            "sleepEndTimestampGMT": _ms(start + timedelta(seconds=s.sleep_s + awake)),
            "sleepScores": {"overall": {"value": s.sleep_score, "qualifierKey": qualifier}},
        }
    }


def _hrv(s: DayState) -> dict[str, Any]:
    baseline = None
    status = "NONE"
    if s.hrv_baseline is not None and s.hrv_weekly_avg is not None:
        low, high = s.hrv_baseline
        baseline = {"balancedLow": low, "balancedUpper": high}
        status = "LOW" if s.hrv_weekly_avg < low else "UNBALANCED" if s.hrv_weekly_avg > high else "BALANCED"
    return {
        "hrvSummary": {
            "calendarDate": s.day.isoformat(),
            "weeklyAvg": s.hrv_weekly_avg,
            "lastNightAvg": s.hrv,
            "lastNight5MinHigh": s.hrv + 18,
            "baseline": baseline,
            "status": status,
        }
    }


def _readiness(s: DayState) -> list[dict[str, Any]]:
    """A morning reading, plus a lower one after training on days with an activity."""
    readings = [(7.5, s.readiness, "AFTER_WAKEUP_RESET")]
    if s.activities:
        readings.append((20.0, max(1, s.readiness - 12), "AFTER_POST_EXERCISE_RESET"))
    out = []
    for hour, score, context in readings:
        level = _readiness_level(score)
        moment = datetime.combine(s.day, datetime.min.time()) + timedelta(hours=hour)
        out.append(
            {
                "calendarDate": s.day.isoformat(),
                "timestamp": moment.strftime("%Y-%m-%dT%H:%M:%S.0"),
                "score": score,
                "level": level,
                "feedbackShort": READINESS_FEEDBACK[level],
                "feedbackLong": READINESS_FEEDBACK[level],
                "inputContext": context,
            }
        )
    return out


def _training_status(s: DayState) -> dict[str, Any]:
    ratio = round(s.acute_load / s.chronic_load, 1) if s.chronic_load else None
    acwr_status = "NONE" if ratio is None else "LOW" if ratio < 0.8 else "HIGH" if ratio > 1.3 else "OPTIMAL"
    return {
        "userId": USER_ID,
        "mostRecentVO2Max": {
            "generic": {
                "calendarDate": s.day.isoformat(),
                "vo2MaxPreciseValue": s.vo2max,
                "vo2MaxValue": round(s.vo2max),
            }
        },
        "mostRecentTrainingStatus": {
            "latestTrainingStatusData": {
                DEVICE_ID: {
                    "calendarDate": s.day.isoformat(),
                    "trainingStatus": STATUS_CODES[s.status_phrase.rsplit("_", 1)[0]],
                    "trainingStatusFeedbackPhrase": s.status_phrase,
                    "primaryTrainingDevice": True,
                    "acuteTrainingLoadDTO": {
                        "dailyTrainingLoadAcute": s.acute_load,
                        "dailyTrainingLoadChronic": s.chronic_load,
                        "dailyAcuteChronicWorkloadRatio": ratio,
                        "acwrStatus": acwr_status,
                    },
                }
            }
        },
    }


def _weigh_ins(s: DayState) -> dict[str, Any]:
    entries = []
    for i, weight in enumerate(s.weigh_ins):
        moment = datetime.combine(s.day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=6, minutes=10 * i)
        entries.append(
            {
                "samplePk": int(moment.timestamp()) * 10 + i,
                "calendarDate": s.day.isoformat(),
                "timestampGMT": _ms(moment),
                "weight": round(weight * 1000),
                "bmi": round(weight / HEIGHT_M**2, 1),
                "bodyFat": s.body_fat_pct,
                "bodyWater": s.body_water_pct,
                "muscleMass": round(s.muscle_mass_kg * 1000),
                "boneMass": 5_500,
                "sourceType": "INDEX_SCALE",
            }
        )
    return {"startDate": s.day.isoformat(), "endDate": s.day.isoformat(), "dateWeightList": entries}


def _race_predictions(s: DayState) -> list[dict[str, Any]]:
    day = s.day.isoformat()
    return [{"userId": USER_ID, "fromCalendarDate": day, "toCalendarDate": day, "calendarDate": day, **s.predicted_s}]


def _readiness_level(score: int) -> str:
    if score >= 95:
        return "PRIME"
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MODERATE"
    if score >= 25:
        return "LOW"
    return "POOR"


def _ms(moment: datetime) -> int:
    return round(moment.timestamp() * 1000)
