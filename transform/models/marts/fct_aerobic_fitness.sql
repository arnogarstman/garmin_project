-- One row per Monday-to-Sunday week with runs in the 6 weeks up to its Sunday: aerobic fitness from
-- steady runs (no races, at least 3 km, between 4:00 and 9:00 min/km, with heart rate).
-- Efficiency is speed in m/min per beat; heart rate at a reference pace comes from a least-squares
-- line of average heart rate on pace over those runs, so a mix of easy and fast runs still gives
-- the heart rate one fixed pace costs. The reference pace is the median pace of all steady runs,
-- to the nearest 15 seconds, so it sits where the data is densest.
with runs as (
    select
        activity_date,
        distance_km,
        pace_min_per_km,
        avg_hr,
        (1000 / pace_min_per_km) / avg_hr as efficiency
    from {{ ref('fct_activities') }}
    where
        activity_type ilike '%run%'
        and distance_km >= 3
        and pace_min_per_km between 4 and 9
        and avg_hr > 0
        and not coalesce(is_tagged_race, false)
),

reference as (
    select round(median(pace_min_per_km) * 4) / 4 as ref_pace_min_per_km from runs
),

-- Every week from the first steady run to the last, so a week without one still shows the 6 weeks before.
weeks as (
    select unnest(generate_series(
        min(date_trunc('week', activity_date)), max(date_trunc('week', activity_date)), interval 7 day
    ))::date as week_start
    from runs
),

windowed as (
    select
        w.week_start,
        count(*) as runs,
        sum(r.efficiency * r.distance_km) / sum(r.distance_km) as efficiency,
        regr_slope(r.avg_hr, r.pace_min_per_km) as hr_per_min_pace,
        regr_intercept(r.avg_hr, r.pace_min_per_km) as hr_intercept,
        min(r.pace_min_per_km) as fastest_pace,
        max(r.pace_min_per_km) as slowest_pace,
        avg(r.avg_hr) as avg_hr
    from weeks as w
    inner join runs as r on r.activity_date between w.week_start - 35 and w.week_start + 6
    group by w.week_start
)

select
    w.week_start,
    w.runs,
    w.efficiency,
    reference.ref_pace_min_per_km,
    -- The line needs runs at more than one pace, and is read only inside the paces it was fitted on.
    case
        when
            w.runs >= 4
            and w.slowest_pace - w.fastest_pace >= 0.3
            and reference.ref_pace_min_per_km between w.fastest_pace - 0.25 and w.slowest_pace + 0.25
            then w.hr_intercept + w.hr_per_min_pace * reference.ref_pace_min_per_km
    end as hr_at_ref_pace,
    w.avg_hr
from windowed as w
cross join reference
