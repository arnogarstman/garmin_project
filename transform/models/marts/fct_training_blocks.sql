-- One row per Monday-to-Sunday week: the 4-week training block ending that week, and how the half
-- marathon prediction and VO2 max moved from the day before the block to 2 weeks after it (time to
-- adapt). The base for asking which kind of training moves the predictions. Blocks overlap by three
-- weeks, so neighbouring rows are not independent.
with weeks as (
    select distinct date_trunc('week', calendar_date)::date as week_start
    from {{ ref('fct_race_predictions') }}
),

blocks as (
    select
        week_start,
        week_start - 21 as block_start,
        week_start + 6 as block_end,
        week_start + 20 as outcome_date
    from weeks
),

runs as (
    select * from {{ ref('fct_activities') }}
    where activity_type ilike '%run%' and distance_km > 0
),

block_runs as (
    select
        b.week_start,
        sum(r.distance_km) / 4 as run_km_per_week,
        count(r.activity_id) / 4 as runs_per_week,
        count(distinct r.activity_date) as run_days,
        max(r.distance_km) as longest_run_km,
        count(*) filter (where r.distance_km >= 15) as runs_15k_plus,
        sum(r.hr_zone_1_min + r.hr_zone_2_min) as easy_min,
        sum(r.hr_zone_3_min) as tempo_min,
        sum(r.hr_zone_4_min + r.hr_zone_5_min) as hard_min,
        sum(
            r.hr_zone_1_min + r.hr_zone_2_min + r.hr_zone_3_min + r.hr_zone_4_min + r.hr_zone_5_min
        ) as zone_min,
        sum(r.training_load) / 4 as load_per_week
    from blocks as b
    left join runs as r on r.activity_date between b.block_start and b.block_end
    group by b.week_start
),

predictions as (
    select calendar_date, predicted_half_marathon_s
    from {{ ref('fct_race_predictions') }}
    where predicted_half_marathon_s is not null
),

vo2 as (
    select calendar_date, vo2max from {{ ref('fct_daily_health') }} where vo2max is not null
),

-- The latest reading on or before each day, so a missing day takes the one before it.
before_block as (
    select b.week_start, p.predicted_half_marathon_s as hm_before_s
    from blocks as b
    asof left join predictions as p on b.block_start - 1 >= p.calendar_date
),

after_block as (
    select b.week_start, p.predicted_half_marathon_s as hm_after_s, p.calendar_date as hm_after_date
    from blocks as b
    asof left join predictions as p on b.outcome_date >= p.calendar_date
),

vo2_before as (
    select b.week_start, v.vo2max as vo2max_before
    from blocks as b
    asof left join vo2 as v on b.block_start - 1 >= v.calendar_date
),

vo2_after as (
    select b.week_start, v.vo2max as vo2max_after, v.calendar_date as vo2_after_date
    from blocks as b
    asof left join vo2 as v on b.outcome_date >= v.calendar_date
)

select
    b.week_start,
    b.block_start,
    b.block_end,
    b.outcome_date,
    r.run_km_per_week,
    r.runs_per_week,
    r.run_days,
    r.longest_run_km,
    r.runs_15k_plus,
    r.load_per_week,
    r.easy_min / nullif(r.zone_min, 0) as easy_share,
    r.tempo_min / nullif(r.zone_min, 0) as tempo_share,
    r.hard_min / nullif(r.zone_min, 0) as hard_share,
    bb.hm_before_s,
    -- Only once the outcome date has a reading of its own week: no outcome for blocks still adapting.
    case when ab.hm_after_date > b.outcome_date - 7 then ab.hm_after_s end as hm_after_s,
    case
        when ab.hm_after_date > b.outcome_date - 7 then ab.hm_after_s / bb.hm_before_s - 1
    end as hm_change,
    vb.vo2max_before,
    case when va.vo2_after_date > b.outcome_date - 7 then va.vo2max_after - vb.vo2max_before end as vo2max_change
from blocks as b
left join block_runs as r using (week_start)
left join before_block as bb using (week_start)
left join after_block as ab using (week_start)
left join vo2_before as vb using (week_start)
left join vo2_after as va using (week_start)
