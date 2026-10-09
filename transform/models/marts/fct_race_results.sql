-- Half marathon and marathon results with progression per distance. A run
-- counts when Garmin marks it as a race, or when its recorded distance falls in
-- the band around the official distance (GPS usually measures a little long).
-- Long training runs of exactly race distance also match; is_tagged_race tells
-- them apart once races are marked as such in Garmin Connect.
with distances as (
    select * from (
        values
            ('Half marathon', 21.0975, 20.8, 21.9),
            ('Marathon', 42.195, 41.8, 43.5)
    ) as t (race_distance, official_km, min_km, max_km)
),

runs as (
    select *
    from {{ ref('stg_garmin__activities') }}
    where activity_type in (
        'running', 'street_running', 'track_running', 'trail_running', 'treadmill_running', 'virtual_run'
    )
),

results as (
    select
        runs.activity_id,
        runs.started_at_local::date as race_date,
        runs.activity_name,
        distances.race_distance,
        distances.official_km,
        runs.distance_m / 1000 as distance_km,
        runs.duration_s as finish_time_s,
        (runs.duration_s / 60) / (runs.distance_m / 1000) as pace_min_per_km,
        runs.avg_hr,
        runs.max_hr,
        runs.event_type = 'race' as is_tagged_race
    from runs
    inner join distances
        on runs.distance_m / 1000 between distances.min_km and distances.max_km
)

select
    *,
    row_number() over w as race_number,
    lag(finish_time_s) over w as previous_finish_time_s,
    lag(finish_time_s) over w - finish_time_s as improvement_vs_previous_s,
    first_value(finish_time_s) over w - finish_time_s as improvement_vs_first_s,
    min(finish_time_s) over w as personal_best_to_date_s,
    finish_time_s < coalesce(min(finish_time_s) over (w rows between unbounded preceding and 1 preceding), 'infinity')
        as is_personal_best
from results
window w as (partition by race_distance order by race_date, activity_id)
