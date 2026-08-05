SELECT
    (SELECT count(*) FROM raw_.lastfm_tag_snapshots) AS tag_count,
    (SELECT count(*) FROM raw_.lastfm_artist_snapshots) AS artist_count,
    (
        SELECT count(DISTINCT fetched_at)
        FROM raw_.lastfm_tag_snapshots
    ) AS tag_poll_count;

