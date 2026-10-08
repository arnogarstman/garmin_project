{{ config(materialized='view') }}

-- When Garmin last received each kind of data, as seen at the latest ingest,
-- plus the ingest itself. A view, so ages are relative to query time. A signal
-- with a threshold but no timestamp counts as stale: freshness that cannot be
-- confirmed should not look fine. Activities have no threshold (rest days).
with signals as (
    select 'last ingest' as signal, max(loaded_at_utc) as observed_at_utc, 24 as stale_after_hours
    from {{ ref('stg_garmin__device_syncs') }}
    union all
    select 'device last upload', arg_max(last_uploaded_at_utc, loaded_at_utc), 12
    from {{ ref('stg_garmin__device_syncs') }}
    union all
    select 'daily summary last sync', max(last_synced_at_utc), 12
    from {{ ref('stg_garmin__daily_summary') }}
    union all
    select 'last night''s sleep end', max(sleep_ended_at_utc), 24
    from {{ ref('stg_garmin__sleep') }}
    union all
    select 'latest activity start', max(started_at_utc), null
    from {{ ref('stg_garmin__activities') }}
)

select
    signal,
    observed_at_utc,
    date_diff('second', observed_at_utc, now() at time zone 'UTC') / 3600.0 as age_hours,
    stale_after_hours,
    stale_after_hours is not null
    and coalesce(age_hours > stale_after_hours, true) as is_stale
from signals
