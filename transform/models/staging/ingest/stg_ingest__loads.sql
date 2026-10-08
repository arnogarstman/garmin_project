select
    load_id,
    source,
    records_fetched,
    records_inserted,
    loaded_at at time zone 'UTC' as loaded_at_utc
from {{ source('ingest', 'loads') }}
