-- Current heart rate zones per sport, with each zone's bpm range.
select
    sport,
    training_method,
    zone_1_floor_bpm,
    zone_2_floor_bpm,
    zone_3_floor_bpm,
    zone_4_floor_bpm,
    zone_5_floor_bpm,
    max_hr_bpm,
    lactate_threshold_hr_bpm
from {{ ref('stg_garmin__heart_rate_zones') }}
