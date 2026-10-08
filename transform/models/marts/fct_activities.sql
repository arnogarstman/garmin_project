select
    activity_id,
    activity_name,
    activity_type,
    started_at_local,
    started_at_local::date as activity_date,
    coalesce(distance_m, 0) / 1000 as distance_km,
    coalesce(duration_s, 0) / 60 as duration_min,
    case
        when distance_m > 100 then (duration_s / 60) / (distance_m / 1000)
    end as pace_min_per_km,
    avg_hr,
    max_hr,
    calories,
    elevation_gain_m,
    aerobic_effect,
    anaerobic_effect,
    training_load
from {{ ref('stg_garmin__activities') }}
