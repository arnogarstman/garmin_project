{{ config(materialized='ephemeral') }}

-- Committed raw records only: a load becomes visible once its marker exists in
-- the ingest log, so a run that died halfway never shows up (see ingest/storage.py).
with payloads as (
    select
        json ->> 'load_id' as load_id,
        endpoint,
        json -> 'params' as params,
        json -> 'payload' as payload,
        (json ->> 'loaded_at')::timestamptz as loaded_at
    from {{ source('garmin', 'payloads') }}
)

select *
from payloads
where load_id in (select load_id from {{ ref('stg_ingest__loads') }})
