SELECT
    (
        SELECT count(*)
        FROM mart_.genre_weekly
        WHERE week_start = ? AND opportunity IS NOT NULL
    ) AS opportunity_rows,
    (SELECT count(*) FROM mart_.genre_weekly) AS history_rows,
    (SELECT count(*) FROM mart_.ecosystem_weekly) AS ecosystem_rows,
    (SELECT count(*) FROM fcst_.predictions) AS forecast_rows,
    (SELECT count(*) FROM fcst_.next_up) AS next_up_rows,
    (
        SELECT count(*)
        FROM mart_.briefs
        WHERE week_start = ?
    ) AS brief_rows,
    (
        SELECT count(*)
        FROM mart_.scene_map
        WHERE as_of_week = ?
    ) AS scene_rows,
    (
        SELECT count(*)
        FROM mart_.conversation_evidence
        WHERE week_start = ?
    ) AS conversation_receipts,
    (
        SELECT count(*)
        FROM mart_.listening_evidence
        WHERE week_start = ?
    ) AS listening_receipts,
    (
        SELECT count(*)
        FROM mart_.supply_evidence
        WHERE week_start = ?
    ) AS supply_receipts,
    (
        SELECT trigger_name
        FROM mart_.pipeline_runs
        ORDER BY started_at DESC, run_id DESC
        LIMIT 1
    ) AS trigger_name;
