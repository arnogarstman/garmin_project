-- Body composition per day with at least one weigh-in: the average of that
-- day's readings, so several weigh-ins on one day do not skew the trend.
select
    calendar_date,
    count(*) as weigh_ins,
    avg(weight_kg) as weight_kg,
    avg(bmi) as bmi,
    avg(body_fat_pct) as body_fat_pct,
    avg(body_water_pct) as body_water_pct,
    avg(muscle_mass_kg) as muscle_mass_kg,
    avg(bone_mass_kg) as bone_mass_kg
from {{ ref('stg_garmin__weigh_ins') }}
group by calendar_date
