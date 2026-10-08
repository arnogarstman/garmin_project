{{ config(materialized='view') }}

-- Per metric: latest day with data, how far behind today that is, and how
-- complete the metric is over everything ingested. A view, so days_behind
-- is relative to query time.
select
    metric,
    max(calendar_date) filter (where is_present) as latest_date,
    current_date - max(calendar_date) filter (where is_present) as days_behind,
    round(avg(is_present::integer) * 100, 1) as completeness_pct
from {{ ref('rpt_metric_coverage') }}
group by metric
order by metric
