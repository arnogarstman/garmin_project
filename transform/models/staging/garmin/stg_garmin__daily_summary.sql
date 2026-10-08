with latest as (
    {{ garmin_latest_daily('daily_summary') }}
)

select
    calendar_date,
    (payload ->> '$.restingHeartRate')::integer as resting_hr,
    (payload ->> '$.totalSteps')::integer as steps,
    (payload ->> '$.totalKilocalories')::double as calories,
    (payload ->> '$.averageStressLevel')::integer as avg_stress,
    (payload ->> '$.bodyBatteryChargedValue')::integer as body_battery_charged,
    (payload ->> '$.bodyBatteryDrainedValue')::integer as body_battery_drained,
    (payload ->> '$.bodyBatteryHighestValue')::integer as body_battery_highest,
    (payload ->> '$.bodyBatteryLowestValue')::integer as body_battery_lowest,
    (payload ->> '$.bodyBatteryMostRecentValue')::integer as body_battery_most_recent,
    (payload ->> '$.sleepingSeconds')::integer as sleeping_seconds,
    (payload ->> '$.lastSyncTimestampGMT')::timestamp as last_synced_at_utc,
    loaded_at_utc
from latest
