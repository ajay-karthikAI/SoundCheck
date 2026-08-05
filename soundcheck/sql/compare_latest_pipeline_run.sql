SELECT
    run_id,
    status,
    started_at,
    completed_at,
    wall_time_seconds,
    run_kind
FROM mart_.pipeline_runs
WHERE run_kind = 'weekly'
ORDER BY started_at DESC, run_id DESC
LIMIT 1;
