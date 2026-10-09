{{ config(materialized='ephemeral') }}

-- This source's rows of the shared raw table. A load and its run-log row are
-- written in one transaction (see ingest/storage.py), so every row is committed.
select
    load_id,
    endpoint,
    params,
    payload,
    loaded_at
from {{ source('garmin', 'payloads') }}
where source = 'garmin'
