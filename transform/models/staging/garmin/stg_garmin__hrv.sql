with latest as (
    {{ garmin_latest_daily('hrv') }}
)

select
    calendar_date,
    (payload ->> '$.hrvSummary.lastNightAvg')::integer as hrv_last_night_avg,
    (payload ->> '$.hrvSummary.lastNight5MinHigh')::integer as hrv_last_night_5min_high,
    (payload ->> '$.hrvSummary.weeklyAvg')::integer as hrv_weekly_avg,
    (payload ->> '$.hrvSummary.baseline.balancedLow')::integer as hrv_baseline_low,
    (payload ->> '$.hrvSummary.baseline.balancedUpper')::integer as hrv_baseline_high,
    payload ->> '$.hrvSummary.status' as hrv_status,
    loaded_at_utc
from latest
