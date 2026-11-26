-- One row per complete day: Garmin's average daily burn over the 28 days up to it, the weight trend
-- over the same days (least-squares slope of the weigh-ins) and the daily balance that trend implies
-- at 7700 kcal per kg. Burn plus balance is the intake the trend implies if Garmin's burn is right.
-- Needs 6 weigh-ins spread over at least 14 of those days.
with days as (
    select
        calendar_date,
        total_kcal,
        weight_kg,
        calendar_date - date '2000-01-01' as day_number
    from {{ ref('fct_daily_energy') }}
    where calendar_date < current_date and total_kcal > 0
),

rolling as (
    select
        calendar_date,
        avg(total_kcal) over last28 as burn_kcal,
        count(total_kcal) over last28 as burn_days,
        regr_slope(weight_kg, day_number) over last28 as weight_kg_per_day,
        count(weight_kg) over last28 as weigh_ins,
        max(case when weight_kg is not null then day_number end) over last28
        - min(case when weight_kg is not null then day_number end) over last28 as weigh_in_span_days,
        avg(weight_kg) over last28 as weight_kg
    from days
    window last28 as (order by calendar_date range between interval 27 day preceding and current row)
)

select
    calendar_date,
    burn_kcal,
    burn_days,
    weight_kg,
    weigh_ins,
    case when weigh_ins >= 6 and weigh_in_span_days >= 14 then weight_kg_per_day * 7 end as weight_kg_per_week,
    case when weigh_ins >= 6 and weigh_in_span_days >= 14 then weight_kg_per_day * 7700 end as balance_kcal,
    case
        when weigh_ins >= 6 and weigh_in_span_days >= 14 then burn_kcal + weight_kg_per_day * 7700
    end as implied_intake_kcal
from rolling
where burn_days >= 21
