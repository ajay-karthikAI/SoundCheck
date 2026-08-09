SET TimeZone = 'UTC';

WITH settings AS (
    SELECT CAST(? AS TIMESTAMPTZ) AS as_of
),
latest_posts AS (
    SELECT
        uri,
        created_at,
        row_number() OVER (
            PARTITION BY uri
            ORDER BY ingested_at DESC
        ) AS recency_rank
    FROM raw_.bluesky_posts
),
preferred_links AS (
    SELECT
        post_uri,
        artist_mbid,
        artist_name_raw
    FROM stg_.post_artist_links
    QUALIFY row_number() OVER (
        PARTITION BY post_uri
        ORDER BY
            (join_key_type = 'mbid') DESC,
            score DESC
    ) = 1
),
final_engagement AS (
    SELECT
        post.uri,
        engagement.like_count,
        engagement.repost_count,
        engagement.reply_count,
        engagement.fetched_at
    FROM latest_posts AS post
    JOIN raw_.bluesky_engagement AS engagement
        ON engagement.uri = post.uri
    WHERE
        post.recency_rank = 1
        AND (
            engagement.poll_target_hours = 72
            OR (
                engagement.poll_target_hours IS NULL
                AND engagement.fetched_at >= post.created_at + INTERVAL 60 HOUR
            )
        )
    QUALIFY row_number() OVER (
        PARTITION BY post.uri
        ORDER BY engagement.fetched_at DESC
    ) = 1
),
lastfm_artist_base AS (
    SELECT
        CASE
            WHEN mbid IS NOT NULL THEN 'mbid:' || lower(mbid)
            ELSE 'name:' || lower(trim(artist_name))
        END AS artist_key,
        artist_name,
        mbid AS artist_mbid,
        tags,
        source_genres,
        fetched_at
    FROM raw_.lastfm_artist_snapshots
    QUALIFY row_number() OVER (
        PARTITION BY
            CASE
                WHEN mbid IS NOT NULL THEN 'mbid:' || lower(mbid)
                ELSE 'name:' || lower(trim(artist_name))
            END
        ORDER BY fetched_at DESC
    ) = 1
),
lastfm_artist_tags AS (
    SELECT
        artist_key,
        artist_name,
        artist_mbid,
        trim(unnest(tags)) AS raw_tag
    FROM lastfm_artist_base

    UNION

    SELECT
        artist_key,
        artist_name,
        artist_mbid,
        trim(unnest(source_genres)) AS raw_tag
    FROM lastfm_artist_base
),
lastfm_artist_genres AS (
    SELECT DISTINCT
        source.artist_mbid,
        source.artist_name,
        mapping.canonical_genre
    FROM lastfm_artist_tags AS source
    INNER JOIN stg_.tag_genre_map AS mapping
        ON
            mapping.source_system = 'lastfm'
            AND lower(trim(mapping.raw_tag)) = lower(source.raw_tag)
    WHERE source.raw_tag <> ''
),
musicbrainz_release_tags AS (
    SELECT
        release.release_group_mbid,
        trim(unnest(release.genres)) AS raw_tag,
        'musicbrainz_genre' AS source_system
    FROM raw_.mb_release_groups AS release

    UNION

    SELECT
        release.release_group_mbid,
        trim(source_tag.name) AS raw_tag,
        'musicbrainz_tag' AS source_system
    FROM
        raw_.mb_release_groups AS release,
        unnest(release.tags) AS expanded(source_tag)
),
musicbrainz_release_genres AS (
    SELECT DISTINCT
        source.release_group_mbid,
        mapping.canonical_genre
    FROM musicbrainz_release_tags AS source
    INNER JOIN stg_.tag_genre_map AS mapping
        ON
            mapping.source_system = source.source_system
            AND lower(trim(mapping.raw_tag)) = lower(source.raw_tag)
    WHERE source.raw_tag <> ''
),
musicbrainz_artist_genres AS (
    SELECT DISTINCT
        credit.mbid AS artist_mbid,
        credit.artist_name,
        genre.canonical_genre
    FROM
        raw_.mb_release_groups AS release,
        unnest(release.artist_credits) AS expanded(credit)
    INNER JOIN musicbrainz_release_genres AS genre
        ON genre.release_group_mbid = release.release_group_mbid
),
artist_genres AS (
    SELECT * FROM lastfm_artist_genres
    UNION
    SELECT * FROM musicbrainz_artist_genres
),
post_genres AS (
    SELECT DISTINCT
        post.uri,
        CAST(date_trunc('week', post.created_at) AS DATE) AS week_start,
        artist.canonical_genre
    FROM latest_posts AS post
    INNER JOIN preferred_links AS link
        ON link.post_uri = post.uri
    INNER JOIN artist_genres AS artist
        ON (
            link.artist_mbid IS NOT NULL
            AND artist.artist_mbid = link.artist_mbid
        ) OR (
            link.artist_mbid IS NULL
            AND lower(trim(artist.artist_name)) = lower(trim(link.artist_name_raw))
        )
    WHERE post.recency_rank = 1
)
SELECT
    post.week_start,
    post.canonical_genre,
    post.uri AS post_uri,
    1 AS mentions,
    engagement.like_count AS likes,
    engagement.repost_count AS reposts,
    engagement.reply_count AS replies,
    engagement.fetched_at AS engagement_fetched_at,
    CASE
        WHEN engagement.uri IS NOT NULL THEN 'complete'
        WHEN settings.as_of < post.week_start + INTERVAL 7 DAY THEN 'awaiting_72h'
        ELSE 'overdue_72h'
    END AS engagement_maturity_status
FROM post_genres AS post
CROSS JOIN settings
LEFT JOIN final_engagement AS engagement
    ON engagement.uri = post.uri
ORDER BY post.week_start, post.canonical_genre, post.uri;
