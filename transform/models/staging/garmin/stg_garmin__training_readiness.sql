-- Garmin recomputes readiness during the day (after wake-up, after activities),
-- so a day holds several readings. One row per reading.
with latest as (
    {{ garmin_latest_daily('training_readiness') }}
),

readings as (
    select
        calendar_date,
        loaded_at_utc,
        unnest(payload::json []) as reading
    from latest
)

select
    calendar_date,
    (reading ->> '$.timestamp')::timestamp as measured_at_utc,
    (reading ->> '$.score')::integer as readiness_score,
    reading ->> '$.level' as readiness_level,
    reading ->> '$.feedbackShort' as feedback_short,
    reading ->> '$.feedbackLong' as feedback_long,
    reading ->> '$.inputContext' as input_context,
    row_number() over (
        partition by calendar_date order by (reading ->> '$.timestamp')::timestamp desc
    ) = 1 as is_latest_of_day,
    loaded_at_utc
from readings
