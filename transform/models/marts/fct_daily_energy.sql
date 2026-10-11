-- Energy per day: what Garmin counts as burned (resting plus active), the day's workouts and
-- the weigh-in average, for energy budgets such as the meal plan on the page.
with workouts as (
    select
        activity_date,
        count(*) as workouts,
        sum(calories) as workout_kcal,
        sum(training_load) as training_load,
        sum(case when activity_type ilike '%run%' then distance_km else 0 end) as run_km
    from {{ ref('fct_activities') }}
    group by activity_date
)

select
    h.calendar_date,
    h.calories as total_kcal,
    h.steps,
    coalesce(w.workouts, 0) as workouts,
    w.workout_kcal,
    w.training_load,
    w.run_km,
    b.weight_kg,
    b.body_fat_pct
from {{ ref('fct_daily_health') }} as h
left join workouts as w on h.calendar_date = w.activity_date
left join {{ ref('fct_daily_body') }} as b on h.calendar_date = b.calendar_date
