-- Training status is reported per device; keep the primary training device.
-- The status label comes from Garmin's feedback phrase (e.g. PEAKING_1), since
-- the numeric trainingStatus code is undocumented.
with latest as (
    {{ garmin_latest_daily('training_status') }}
),

by_device as (
    select
        calendar_date,
        payload,
        loaded_at_utc,
        json_extract(payload, '$.mostRecentTrainingStatus.latestTrainingStatusData.*') as statuses
    from latest
),

primary_device as (
    select
        *,
        coalesce(
            list_filter(statuses, s -> (s ->> '$.primaryTrainingDevice')::boolean)[1],
            statuses[1]
        ) as status
    from by_device
)

select
    calendar_date,
    (status ->> '$.trainingStatus')::integer as training_status_code,
    regexp_replace(status ->> '$.trainingStatusFeedbackPhrase', '_\d+$', '') as training_status,
    status ->> '$.trainingStatusFeedbackPhrase' as training_status_feedback,
    (status ->> '$.acuteTrainingLoadDTO.dailyTrainingLoadAcute')::double as acute_load,
    (status ->> '$.acuteTrainingLoadDTO.dailyTrainingLoadChronic')::double as chronic_load,
    (status ->> '$.acuteTrainingLoadDTO.dailyAcuteChronicWorkloadRatio')::double as acwr,
    status ->> '$.acuteTrainingLoadDTO.acwrStatus' as acwr_status,
    coalesce(
        (payload ->> '$.mostRecentVO2Max.generic.vo2MaxPreciseValue')::double,
        (payload ->> '$.mostRecentVO2Max.generic.vo2MaxValue')::double
    ) as vo2max,
    (payload ->> '$.mostRecentVO2Max.generic.calendarDate')::date as vo2max_measured_on,
    loaded_at_utc
from primary_device
