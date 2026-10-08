-- Which metric is present for which day. Gaps on the latest day usually mean
-- the watch has not synced yet; older gaps mean it was not worn or the
-- feature was unavailable.
with metrics as (
    select
        calendar_date,
        unnest([
            {'metric': 'summary', 'is_present': resting_hr is not null},
            {'metric': 'steps', 'is_present': steps is not null},
            {'metric': 'stress', 'is_present': avg_stress is not null},
            {'metric': 'body_battery', 'is_present': body_battery_highest is not null},
            {'metric': 'sleep', 'is_present': sleep_score is not null},
            {'metric': 'hrv', 'is_present': hrv_last_night_avg is not null},
            {'metric': 'readiness', 'is_present': readiness_score is not null}
        ], recursive := true)
    from {{ ref('fct_daily_health') }}
)

select calendar_date, metric, is_present
from metrics
