-- Garmin Coach's plan, day by day: what the adaptive plan scheduled and whether it was done.
select
    calendar_date,
    workout_name,
    description,
    estimated_duration_s / 60 as duration_min,
    training_effect,
    priority,
    status,
    sport,
    is_long,
    is_rest_day,
    plan_name,
    plan_end_date,
    workout_uuid
from {{ ref('stg_garmin__coach_workouts') }}
