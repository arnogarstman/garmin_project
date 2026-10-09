select
    json ->> 'load_id' as load_id,
    source,
    (json ->> 'records_fetched')::integer as records_fetched,
    (json ->> 'records_inserted')::integer as records_inserted,
    (json ->> 'loaded_at')::timestamptz at time zone 'UTC' as loaded_at_utc
from {{ source('ingest', 'loads') }}
