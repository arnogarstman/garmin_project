with reviews as (
    select
        (params ->> '$.activity_id')::bigint as activity_id,
        params ->> '$.model' as model,
        (params ->> '$.prompt_version')::integer as prompt_version,
        payload,
        loaded_at at time zone 'UTC' as reviewed_at_utc
    from {{ source('coach', 'payloads') }}
    where source = 'coach' and endpoint = 'workout_review'
)

select
    activity_id,
    payload ->> '$.status' as status,
    payload ->> '$.headline' as headline,
    payload ->> '$.session_type' as session_type,
    payload ->> '$.summary' as summary,
    payload ->> '$.went_well[*]' as went_well,
    payload ->> '$.watch_out[*]' as watch_out,
    payload ->> '$.recovery' as recovery,
    payload ->> '$.next_session' as next_session,
    model,
    prompt_version,
    reviewed_at_utc
from reviews
qualify row_number() over (partition by activity_id order by reviewed_at_utc desc) = 1
