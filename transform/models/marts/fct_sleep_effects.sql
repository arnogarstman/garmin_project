-- One row per night with sleep, attributed to the day it ends, beside what followed that day:
-- the morning's recovery readings, the day's runs and the morning weigh-in. The base for asking
-- whether a night's sleep shows up in running and weight.
--
-- Run performance is aerobic efficiency (speed in m/min per beat of average heart rate), compared
-- with the runner's own runs of the 42 days before, so fitness gained over months does not read as
-- an effect of sleep. Races and runs under 2 km or without heart rate are left out.
with sleep as (
    select
        calendar_date,
        sleep_seconds / 3600 as sleep_hours,
        sleep_score,
        deep_sleep_seconds / nullif(sleep_seconds, 0) as deep_share,
        rem_sleep_seconds / nullif(sleep_seconds, 0) as rem_share,
        awake_seconds / 60 as awake_min,
        -- Bedtime as hours after midnight of the evening before: 23:30 is 23.5, 00:30 is 24.5.
        hour(sleep_started_at_local) + minute(sleep_started_at_local) / 60
        + case when hour(sleep_started_at_local) < 12 then 24 else 0 end as bedtime_hour
    from {{ ref('stg_garmin__sleep') }}
    where sleep_seconds > 0
),

runs as (
    select
        activity_date,
        started_at_local,
        distance_km,
        duration_min,
        avg_hr,
        training_load,
        (1000 / pace_min_per_km) / avg_hr as efficiency
    from {{ ref('fct_activities') }}
    where
        activity_type ilike '%run%'
        and distance_km >= 2
        and avg_hr > 0
        and pace_min_per_km is not null
        and not coalesce(is_tagged_race, false)
),

runs_vs_base as (
    select
        *,
        avg(efficiency) over recent as base_efficiency,
        count(*) over recent as base_runs
    from runs
    window recent as (
        order by started_at_local
        range between interval 42 day preceding and interval 1 minute preceding
    )
),

run_days as (
    select
        activity_date,
        count(*) as runs,
        sum(distance_km) as run_km,
        sum(duration_min) / sum(distance_km) as run_pace_min_per_km,
        sum(avg_hr * duration_min) / sum(duration_min) as run_avg_hr,
        sum(training_load) as run_load,
        sum(efficiency * distance_km) / sum(distance_km) as run_efficiency,
        sum(case when base_runs >= 3 then (efficiency / base_efficiency - 1) * distance_km end)
        / sum(case when base_runs >= 3 then distance_km end) as run_efficiency_vs_base
    from runs_vs_base
    group by activity_date
),

body as (
    select
        calendar_date,
        weight_kg,
        weight_kg - lag(weight_kg) over (order by calendar_date) as weight_change_kg,
        calendar_date - lag(calendar_date) over (order by calendar_date) as days_since_weigh_in
    from {{ ref('fct_daily_body') }}
)

select
    sleep.calendar_date,
    sleep.sleep_hours,
    avg(sleep.sleep_hours) over (
        order by sleep.calendar_date range between interval 6 day preceding and current row
    ) as sleep_hours_7d,
    sleep.sleep_score,
    sleep.deep_share,
    sleep.rem_share,
    sleep.awake_min,
    sleep.bedtime_hour,
    health.hrv_last_night_avg as hrv,
    health.resting_hr,
    health.readiness_score,
    coalesce(run_days.runs, 0) as runs,
    run_days.run_km,
    run_days.run_pace_min_per_km,
    run_days.run_avg_hr,
    run_days.run_load,
    run_days.run_efficiency,
    run_days.run_efficiency_vs_base,
    body.weight_kg,
    -- Only a weigh-in the morning before counts, so the change spans one day and this night.
    case when body.days_since_weigh_in = 1 then body.weight_change_kg end as weight_change_kg
from sleep
left join {{ ref('fct_daily_health') }} as health using (calendar_date)
left join run_days on sleep.calendar_date = run_days.activity_date
left join body using (calendar_date)
