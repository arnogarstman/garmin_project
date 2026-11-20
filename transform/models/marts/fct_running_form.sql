-- Running form per run: Garmin's running dynamics, with pace and heart rate for context.
-- Ground contact balance only comes from a chest strap (HRM 600, HRM-Pro), so it marks the runs
-- whose dynamics were measured at the chest rather than estimated at the wrist.
select
    activity_id,
    activity_name,
    started_at_local,
    started_at_local::date as activity_date,
    distance_m / 1000 as distance_km,
    case when distance_m > 100 then (duration_s / 60) / (distance_m / 1000) end as pace_min_per_km,
    avg_hr,
    avg_cadence_spm as cadence_spm,
    avg_stride_length_cm / 100 as stride_length_m,
    avg_ground_contact_ms as ground_contact_ms,
    avg_ground_contact_balance_left_pct as ground_contact_balance_left_pct,
    avg_vertical_oscillation_cm as vertical_oscillation_cm,
    avg_vertical_ratio_pct as vertical_ratio_pct,
    avg_power_w as power_w,
    avg_ground_contact_balance_left_pct is not null as is_chest_strap
from {{ ref('stg_garmin__activities') }}
where activity_type ilike '%run%' and avg_cadence_spm > 0
