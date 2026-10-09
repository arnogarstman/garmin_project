-- One row per weigh-in (a scale reading or a manual entry). Weights arrive in
-- grams; body composition fields are 0 when the reading only measured weight,
-- so 0 is treated as missing.
with latest as (
    {{ garmin_latest_daily('weigh_ins') }}
),

weigh_ins as (
    select
        calendar_date,
        unnest(json_extract(payload, '$.dateWeightList[*]')) as weigh_in,
        loaded_at_utc
    from latest
)

select
    (weigh_in ->> '$.samplePk')::bigint as weigh_in_id,
    calendar_date,
    make_timestamp((weigh_in ->> '$.timestampGMT')::bigint * 1000) as measured_at_utc,
    (weigh_in ->> '$.weight')::double / 1000 as weight_kg,
    nullif((weigh_in ->> '$.bmi')::double, 0) as bmi,
    nullif((weigh_in ->> '$.bodyFat')::double, 0) as body_fat_pct,
    nullif((weigh_in ->> '$.bodyWater')::double, 0) as body_water_pct,
    nullif((weigh_in ->> '$.muscleMass')::double, 0) / 1000 as muscle_mass_kg,
    nullif((weigh_in ->> '$.boneMass')::double, 0) / 1000 as bone_mass_kg,
    weigh_in ->> '$.sourceType' as source_type,
    loaded_at_utc
from weigh_ins
