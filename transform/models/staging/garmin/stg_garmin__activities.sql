-- Each run stores the activity list for its date range; overlapping runs
-- repeat activities, so keep the newest copy of each.
with activities as (
    select
        loaded_at at time zone 'UTC' as loaded_at_utc,
        unnest(payload::json []) as activity
    from {{ source('garmin', 'payloads') }}
    where endpoint = 'activities'
)

select
    (activity ->> '$.activityId')::bigint as activity_id,
    activity ->> '$.activityName' as activity_name,
    activity ->> '$.activityType.typeKey' as activity_type,
    (activity ->> '$.startTimeLocal')::timestamp as started_at_local,
    (activity ->> '$.startTimeGMT')::timestamp as started_at_utc,
    (activity ->> '$.distance')::double as distance_m,
    (activity ->> '$.duration')::double as duration_s,
    (activity ->> '$.movingDuration')::double as moving_duration_s,
    (activity ->> '$.averageHR')::double as avg_hr,
    (activity ->> '$.maxHR')::double as max_hr,
    (activity ->> '$.calories')::double as calories,
    (activity ->> '$.elevationGain')::double as elevation_gain_m,
    (activity ->> '$.aerobicTrainingEffect')::double as aerobic_effect,
    (activity ->> '$.anaerobicTrainingEffect')::double as anaerobic_effect,
    (activity ->> '$.activityTrainingLoad')::double as training_load,
    loaded_at_utc
from activities
qualify row_number() over (partition by activity_id order by loaded_at_utc desc) = 1
