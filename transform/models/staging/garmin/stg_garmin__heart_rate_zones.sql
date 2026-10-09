-- The heart rate zone settings from the latest snapshot, one row per sport
-- (DEFAULT applies to every sport without its own zones). Floors are in bpm.
with latest as (
    select
        payload,
        loaded_at at time zone 'UTC' as loaded_at_utc
    from {{ ref('base_garmin__payloads') }}
    where endpoint = 'heart_rate_zones'
    order by loaded_at desc
    limit 1
),

zones as (
    select
        unnest(json_extract(payload, '$[*]')) as zone_set,
        loaded_at_utc
    from latest
)

select
    zone_set ->> '$.sport' as sport,
    zone_set ->> '$.trainingMethod' as training_method,
    (zone_set ->> '$.zone1Floor')::integer as zone_1_floor_bpm,
    (zone_set ->> '$.zone2Floor')::integer as zone_2_floor_bpm,
    (zone_set ->> '$.zone3Floor')::integer as zone_3_floor_bpm,
    (zone_set ->> '$.zone4Floor')::integer as zone_4_floor_bpm,
    (zone_set ->> '$.zone5Floor')::integer as zone_5_floor_bpm,
    (zone_set ->> '$.maxHeartRateUsed')::integer as max_hr_bpm,
    (zone_set ->> '$.restingHeartRateUsed')::integer as resting_hr_bpm,
    (zone_set ->> '$.lactateThresholdHeartRateUsed')::integer as lactate_threshold_hr_bpm,
    loaded_at_utc
from zones
