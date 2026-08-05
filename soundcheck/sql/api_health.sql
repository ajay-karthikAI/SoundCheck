WITH latest_run AS (
    SELECT *
    FROM mart_.pipeline_runs
    ORDER BY started_at DESC, run_id DESC
    LIMIT 1
)
SELECT
    (SELECT max(week_start) FROM mart_.genre_weekly) AS latest_metric_week,
    (SELECT max(target_week) FROM fcst_.predictions) AS latest_forecast_week,
    (
        SELECT max(week_start)
        FROM mart_.genre_weekly
        WHERE
            opportunity IS NOT NULL
            AND week_start
                < CAST(date_trunc('week', current_date) AS DATE)
    ) AS latest_complete_week,
    (SELECT count(*) FROM mart_.genre_weekly) AS metric_rows,
    (SELECT count(*) FROM fcst_.predictions) AS forecast_rows,
    latest_run.run_id,
    latest_run.run_kind,
    latest_run.trigger_name,
    latest_run.git_sha,
    latest_run.status,
    latest_run.started_at,
    latest_run.completed_at,
    latest_run.wall_time_seconds,
    latest_run.bluesky_posts_ingested,
    latest_run.bluesky_engagement_snapshots_ingested,
    latest_run.lastfm_tag_snapshots_ingested,
    latest_run.lastfm_artist_snapshots_ingested,
    latest_run.musicbrainz_release_groups_ingested,
    latest_run.resolution_posts_attempted,
    latest_run.resolution_links_resolved,
    latest_run.resolution_rate,
    latest_run.metric_rows,
    latest_run.forecast_rows,
    latest_run.brief_rows,
    latest_run.error_message
FROM (SELECT 1) AS singleton
LEFT JOIN latest_run ON true;
