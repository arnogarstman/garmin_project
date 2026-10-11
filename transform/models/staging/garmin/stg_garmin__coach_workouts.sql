-- Garmin Coach workouts from the adaptive plans: each plan load holds the current week's tasks.
-- A workout keeps the state of its newest load, so past weeks stay with their last known status.
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
)

select
    task.taskWorkout.workoutUuid as workout_uuid,
    plan_id,
    plan_name,
    plan_end_date,
    task.calendarDate::date as calendar_date,
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
from plans
where task.taskWorkout.workoutUuid is not null
qualify row_number() over (partition by task.taskWorkout.workoutUuid order by loaded_at desc) = 1
