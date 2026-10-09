-- Garmin's predicted race times for each day, in seconds. Requested one day at
-- a time, so the payload is a list with at most one entry.
with latest as (
    {{ garmin_latest_daily('race_predictions') }}
)

select
    calendar_date,
    (payload ->> '$[0].time5K')::integer as predicted_5k_s,
    (payload ->> '$[0].time10K')::integer as predicted_10k_s,
    (payload ->> '$[0].timeHalfMarathon')::integer as predicted_half_marathon_s,
    (payload ->> '$[0].timeMarathon')::integer as predicted_marathon_s,
    loaded_at_utc
from latest
where json_array_length(payload) > 0
