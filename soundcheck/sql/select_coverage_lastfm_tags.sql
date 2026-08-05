SELECT
    tag,
    fetched_at
FROM raw_.lastfm_tag_snapshots
ORDER BY fetched_at, lower(tag);
