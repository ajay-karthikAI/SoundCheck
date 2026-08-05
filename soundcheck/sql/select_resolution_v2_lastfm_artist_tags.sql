WITH latest AS (
    SELECT
        artist_name,
        nullif(mbid, '') AS mbid,
        tags,
        source_genres,
        fetched_at
    FROM raw_.lastfm_artist_snapshots
    QUALIFY row_number() OVER (
        PARTITION BY coalesce(nullif(mbid, ''), lower(trim(artist_name)))
        ORDER BY fetched_at DESC
    ) = 1
),
expanded AS (
    SELECT
        artist_name,
        mbid,
        unnest(list_distinct(list_concat(tags, source_genres))) AS source_tag,
        fetched_at
    FROM latest
)
SELECT DISTINCT
    artist_name,
    mbid,
    'lastfm' AS source_system,
    trim(source_tag) AS source_tag,
    fetched_at
FROM expanded
WHERE trim(source_tag) <> ''
ORDER BY lower(artist_name), lower(source_tag);
