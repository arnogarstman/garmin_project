select
    r.activity_id,
    a.activity_date,
    a.started_at_local,
    a.activity_name,
    a.activity_type,
    r.status,
    r.headline,
    r.session_type,
    r.summary,
    r.went_well,
    r.watch_out,
    r.recovery,
    r.next_session,
    r.model,
    r.prompt_version,
    r.reviewed_at_utc
from {{ ref('stg_coach__workout_reviews') }} as r
inner join {{ ref('fct_activities') }} as a using (activity_id)
