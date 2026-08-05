SELECT
    tag,
    top_artists,
    top_albums,
    fetched_at
FROM raw_.lastfm_tag_snapshots
QUALIFY row_number() OVER (
    PARTITION BY lower(tag)
    ORDER BY fetched_at DESC
) = 1
ORDER BY lower(tag);
