-- Garmin's predicted race times per day, the best available view of how race
-- fitness develops between actual races.
select
    calendar_date,
    predicted_5k_s,
    predicted_10k_s,
    predicted_half_marathon_s,
    predicted_marathon_s
from {{ ref('stg_garmin__race_predictions') }}
