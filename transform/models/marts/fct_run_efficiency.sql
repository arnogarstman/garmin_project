-- One row per run that can be compared on efficiency: no races, at least 2 km, with pace and heart
-- rate. Efficiency is speed in m/min per beat of average heart rate, against the runs of the 42 days
-- before (null with fewer than 3), so fitness gained over months does not count. Each run also carries
-- the night after it (on the day after the run, where Garmin files that night) and how long before
-- bedtime it ended. Shared by fct_sleep_effects and the page's time-of-day analysis.
with runs as (
    select
        activity_id,
        activity_date,
        started_at_local,
        started_at_local + to_microseconds((duration_min * 60e6)::bigint) as ended_at_local,
        distance_km,
        duration_min,
        pace_min_per_km,
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

with_base as (
    select
        *,
        avg(efficiency) over recent as base_efficiency,
        count(*) over recent as base_runs
    from runs
    window recent as (
        order by started_at_local
        range between interval 42 day preceding and interval 1 minute preceding
    )
)

select
    r.activity_id,
    r.activity_date,
    r.started_at_local,
    r.ended_at_local,
    hour(r.started_at_local) + minute(r.started_at_local) / 60 as start_hour,
    case
        when hour(r.started_at_local) < 11 then 'morning'
        when hour(r.started_at_local) < 15 then 'midday'
        when hour(r.started_at_local) < 18 then 'afternoon'
        else 'evening'
    end as time_of_day,
    r.distance_km,
    r.duration_min,
    r.pace_min_per_km,
    r.avg_hr,
    r.training_load,
    r.efficiency,
    r.base_efficiency,
    r.base_runs,
    case when r.base_runs >= 3 then r.efficiency / r.base_efficiency - 1 end as efficiency_vs_base,
    health.sleep_seconds / 3600 as next_sleep_hours,
    health.sleep_score as next_sleep_score,
    health.hrv_last_night_avg as next_hrv,
    health.resting_hr as next_resting_hr,
    sleep.sleep_started_at_local as next_bedtime_local,
    date_diff('minute', r.ended_at_local, sleep.sleep_started_at_local) / 60 as hours_to_bedtime
from with_base as r
left join {{ ref('fct_daily_health') }} as health on health.calendar_date = r.activity_date + 1
left join {{ ref('stg_garmin__sleep') }} as sleep on sleep.calendar_date = r.activity_date + 1
