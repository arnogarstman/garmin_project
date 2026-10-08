-- One device snapshot per ingest run: when the watch last uploaded to Garmin.
select
    payload ->> '$.lastUsedDeviceName' as device_name,
    make_timestamp((payload ->> '$.lastUsedDeviceUploadTime')::bigint * 1000) as last_uploaded_at_utc,
    loaded_at at time zone 'UTC' as loaded_at_utc
from {{ source('garmin', 'payloads') }}
where endpoint = 'device_last_used'
