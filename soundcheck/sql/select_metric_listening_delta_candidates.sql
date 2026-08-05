SET TimeZone = 'UTC';

WITH snapshot_base AS (
    SELECT
        CASE
            WHEN mbid IS NOT NULL THEN 'mbid:' || lower(mbid)
            ELSE 'name:' || lower(trim(artist_name))
        END AS artist_key,
        artist_name,
        playcount,
        listeners,
        tags,
        source_genres,
        fetched_at
    FROM raw_.lastfm_artist_snapshots
),
weekly_snapshots AS (
    SELECT *
    FROM snapshot_base
    QUALIFY row_number() OVER (
        PARTITION BY
            artist_key,
            CAST(date_trunc('week', fetched_at) AS DATE)
        ORDER BY
            fetched_at DESC,
            lower(artist_name)
    ) = 1
),
ordered_snapshots AS (
    SELECT
        artist_key,
        artist_name,
        playcount,
        listeners,
        tags,
        source_genres,
        fetched_at,
        lag(playcount) OVER (
            PARTITION BY artist_key
            ORDER BY fetched_at
        ) AS previous_playcount,
        lag(listeners) OVER (
            PARTITION BY artist_key
            ORDER BY fetched_at
        ) AS previous_listeners
    FROM weekly_snapshots
),
artist_tags AS (
    SELECT
        artist_key,
        fetched_at,
        trim(unnest(tags)) AS raw_tag
    FROM ordered_snapshots

    UNION

    SELECT
        artist_key,
        fetched_at,
        trim(unnest(source_genres)) AS raw_tag
    FROM ordered_snapshots
),
artist_genres AS (
    SELECT DISTINCT
        source.artist_key,
        source.fetched_at,
        mapping.canonical_genre
    FROM artist_tags AS source
    INNER JOIN stg_.tag_genre_map AS mapping
        ON
            mapping.source_system = 'lastfm'
            AND lower(trim(mapping.raw_tag)) = lower(source.raw_tag)
    WHERE source.raw_tag <> ''
)
SELECT
    CAST(date_trunc('week', snapshot.fetched_at) AS DATE) AS week_start,
    genre.canonical_genre,
    snapshot.artist_key,
    snapshot.artist_name,
    snapshot.playcount,
    snapshot.listeners,
    snapshot.previous_playcount,
    snapshot.previous_listeners
FROM ordered_snapshots AS snapshot
INNER JOIN artist_genres AS genre
    ON
        genre.artist_key = snapshot.artist_key
        AND genre.fetched_at = snapshot.fetched_at
ORDER BY
    week_start,
    genre.canonical_genre,
    snapshot.artist_key;
