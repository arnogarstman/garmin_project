with latest as (
    {{ garmin_latest_daily('sleep') }}
)

select
    calendar_date,
    (payload ->> '$.dailySleepDTO.sleepTimeSeconds')::integer as sleep_seconds,
    (payload ->> '$.dailySleepDTO.deepSleepSeconds')::integer as deep_sleep_seconds,
    (payload ->> '$.dailySleepDTO.lightSleepSeconds')::integer as light_sleep_seconds,
    (payload ->> '$.dailySleepDTO.remSleepSeconds')::integer as rem_sleep_seconds,
    (payload ->> '$.dailySleepDTO.awakeSleepSeconds')::integer as awake_seconds,
    (payload ->> '$.dailySleepDTO.sleepScores.overall.value')::integer as sleep_score,
    payload ->> '$.dailySleepDTO.sleepScores.overall.qualifierKey' as sleep_score_qualifier,
    make_timestamp((payload ->> '$.dailySleepDTO.sleepStartTimestampGMT')::bigint * 1000) as sleep_started_at_utc,
    make_timestamp((payload ->> '$.dailySleepDTO.sleepEndTimestampGMT')::bigint * 1000) as sleep_ended_at_utc,
    loaded_at_utc
from latest
