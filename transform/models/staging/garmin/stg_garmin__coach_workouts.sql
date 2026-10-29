-- Garmin Coach workouts from the adaptive plans: each plan load holds the current week's tasks.
-- Coach replans adaptively and gives a replanned workout a new uuid, so every load can bring a new
-- version of the same day. A day shows the tasks of the newest load whose window (its first to its
-- last task date) covers it; a day no newer load covers keeps its last known version, so past
-- weeks stay with their final status.
with plans as (
    select
        params ->> '$.plan_id' as plan_id,
        payload ->> '$.name' as plan_name,
        (payload ->> '$.endDate')::timestamp::date as plan_end_date,
        unnest(
            from_json(
                payload -> '$.taskList',
                '[{"calendarDate": "VARCHAR", "longWkt": "BOOLEAN", "taskWorkout": {
                    "workoutName": "VARCHAR", "workoutDescription": "VARCHAR",
                    "estimatedDurationInSecs": "DOUBLE", "workoutUuid": "VARCHAR",
                    "priorityType": "VARCHAR", "trainingEffectLabel": "VARCHAR", "restDay": "BOOLEAN",
                    "adaptiveCoachingWorkoutStatus": "VARCHAR", "sportType": {"sportTypeKey": "VARCHAR"}
                }}]'
            )
        ) as task,
        loaded_at
    from {{ ref('base_garmin__payloads') }}
    where endpoint = 'adaptive_training_plan'
),

tasks as (
    select
        *,
        task.calendarDate::date as task_date,
        min(task.calendarDate::date) over (partition by plan_id, loaded_at) as window_start,
        max(task.calendarDate::date) over (partition by plan_id, loaded_at) as window_end
    from plans
),

windows as (
    select distinct plan_id, loaded_at, window_start, window_end from tasks
),

-- The newest load of the plan whose window covers each day.
current_tasks as (
    select tasks.*
    from tasks
    where task.taskWorkout.workoutUuid is not null and loaded_at = (
        select max(w.loaded_at)
        from windows as w
        where w.plan_id = tasks.plan_id and tasks.task_date between w.window_start and w.window_end
    )
)

select
    task.taskWorkout.workoutUuid as workout_uuid,
    plan_id,
    plan_name,
    plan_end_date,
    task_date as calendar_date,
    task.taskWorkout.workoutName as workout_name,
    task.taskWorkout.workoutDescription as description,
    task.taskWorkout.estimatedDurationInSecs as estimated_duration_s,
    task.taskWorkout.trainingEffectLabel as training_effect,
    task.taskWorkout.priorityType as priority,
    task.taskWorkout.adaptiveCoachingWorkoutStatus as status,
    task.taskWorkout.sportType.sportTypeKey as sport,
    coalesce(task.longWkt, false) as is_long,
    coalesce(task.taskWorkout.restDay, false) as is_rest_day,
    loaded_at at time zone 'UTC' as loaded_at_utc
from current_tasks
-- A workout Coach moved to another day appears on both; the newest load decides where it is.
qualify row_number() over (partition by task.taskWorkout.workoutUuid order by loaded_at desc) = 1
