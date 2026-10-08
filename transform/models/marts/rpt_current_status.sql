-- Single row: the most recent known value of each status metric, with the
-- day it is from, so the dashboard can show how current each one is.
with status as (
    select * from {{ ref('stg_garmin__training_status') }}
    where training_status is not null
    order by calendar_date desc
    limit 1
),

readiness as (
    select * from {{ ref('stg_garmin__training_readiness') }}
    order by measured_at_utc desc
    limit 1
),

summary as (
    select
        arg_max(body_battery_most_recent, calendar_date) filter (
            where body_battery_most_recent is not null
        ) as body_battery_current,
        arg_max(resting_hr, calendar_date) filter (where resting_hr is not null) as resting_hr,
        max(calendar_date) filter (where resting_hr is not null) as resting_hr_date
    from {{ ref('stg_garmin__daily_summary') }}
)

select
    status.calendar_date as training_status_date,
    status.training_status,
    status.training_status_feedback,
    status.vo2max,
    status.acwr,
    status.acwr_status,
    readiness.calendar_date as readiness_date,
    readiness.readiness_score,
    readiness.readiness_level,
    coalesce(readiness.feedback_long, readiness.feedback_short) as readiness_feedback,
    summary.body_battery_current,
    summary.resting_hr,
    summary.resting_hr_date
from summary
left join status on true
left join readiness on true
