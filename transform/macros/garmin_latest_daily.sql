{#
    Latest payload per calendar day for a per-day Garmin endpoint. Recent days
    are re-fetched on every run, so the newest load wins.
#}
{% macro garmin_latest_daily(endpoint) %}
    select
        cast(params ->> 'date' as date) as calendar_date,
        payload,
        loaded_at at time zone 'UTC' as loaded_at_utc
    from {{ source('garmin', 'payloads') }}
    where endpoint = '{{ endpoint }}'
    qualify row_number() over (partition by params ->> 'date' order by loaded_at desc) = 1
{% endmacro %}
