-- One row per day that was ingested, combining the per-day Garmin endpoints.
-- Readiness is the day's latest reading.
with days as (
    select calendar_date from {{ ref('stg_garmin__daily_summary') }}
    union
    select calendar_date from {{ ref('stg_garmin__sleep') }}
    union
    select calendar_date from {{ ref('stg_garmin__hrv') }}
    union
    select calendar_date from {{ ref('stg_garmin__training_readiness') }}
    union
    select calendar_date from {{ ref('stg_garmin__training_status') }}
),

readiness as (
    select * from {{ ref('stg_garmin__training_readiness') }}
    where is_latest_of_day
)

select
    days.calendar_date,
    summary.resting_hr,
    summary.steps,
    summary.calories,
    summary.avg_stress,
    summary.body_battery_charged,
    summary.body_battery_drained,
    summary.body_battery_highest,
    summary.body_battery_lowest,
    coalesce(summary.sleeping_seconds, sleep.sleep_seconds) as sleep_seconds,
    sleep.deep_sleep_seconds,
    sleep.light_sleep_seconds,
    sleep.rem_sleep_seconds,
    sleep.awake_seconds,
    sleep.sleep_score,
    hrv.hrv_last_night_avg,
    hrv.hrv_weekly_avg,
    hrv.hrv_status,
    readiness.readiness_score,
    readiness.readiness_level,
    status.training_status,
    status.acute_load,
    status.chronic_load,
    status.acwr,
    status.vo2max
from days
left join {{ ref('stg_garmin__daily_summary') }} as summary using (calendar_date)
left join {{ ref('stg_garmin__sleep') }} as sleep using (calendar_date)
left join {{ ref('stg_garmin__hrv') }} as hrv using (calendar_date)
left join readiness using (calendar_date)
left join {{ ref('stg_garmin__training_status') }} as status using (calendar_date)
