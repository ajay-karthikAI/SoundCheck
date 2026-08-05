SET TimeZone = 'UTC';

DELETE FROM mart_.conversation_evidence;
DELETE FROM mart_.listening_evidence;
DELETE FROM mart_.supply_evidence;

INSERT INTO mart_.conversation_evidence (
    week_start,
    canonical_genre,
    post_uri,
    did,
    created_at,
    text,
    like_count,
    repost_count,
    reply_count,
    weighted_score,
    artist_name_raw,
    resolution_method,
    resolution_score,
    join_key_type
)
WITH latest_posts AS (
    SELECT
        uri,
        did,
        created_at,
        text
    FROM raw_.bluesky_posts
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY ingested_at DESC
    ) = 1
),
latest_engagement AS (
    SELECT
        uri,
        like_count,
        repost_count,
        reply_count
    FROM raw_.bluesky_engagement
    QUALIFY row_number() OVER (
        PARTITION BY uri
        ORDER BY fetched_at DESC
    ) = 1
),
preferred_links AS (
    SELECT
        post_uri,
        artist_name_raw,
        method,
        score,
        join_key_type
    FROM stg_.post_artist_links
    QUALIFY row_number() OVER (
        PARTITION BY post_uri
        ORDER BY
            (join_key_type = 'mbid') DESC,
            score DESC,
            artist_name_raw
    ) = 1
)
SELECT
    metric.week_start,
    metric.canonical_genre,
    post.uri,
    post.did,
    post.created_at,
    post.text,
    coalesce(engagement.like_count, 0),
    coalesce(engagement.repost_count, 0),
    coalesce(engagement.reply_count, 0),
    (
        1
        + 0.5 * coalesce(engagement.like_count, 0)
        + 1.5 * coalesce(engagement.repost_count, 0)
        + coalesce(engagement.reply_count, 0)
    ),
    link.artist_name_raw,
    link.method,
    link.score,
    link.join_key_type
FROM mart_.genre_weekly AS metric
CROSS JOIN unnest(metric.conversation_post_uris) AS receipt(post_uri)
INNER JOIN latest_posts AS post
    ON post.uri = receipt.post_uri
INNER JOIN preferred_links AS link
    ON link.post_uri = post.uri
LEFT JOIN latest_engagement AS engagement
    ON engagement.uri = post.uri;

INSERT INTO mart_.listening_evidence (
    week_start,
    canonical_genre,
    artist_key,
    artist_name,
    artist_mbid,
    playcount_delta,
    listeners_delta,
    weighted_delta,
    fetched_at
)
WITH snapshot_base AS (
    SELECT
        CASE
            WHEN mbid IS NOT NULL THEN 'mbid:' || lower(mbid)
            ELSE 'name:' || lower(trim(artist_name))
        END AS artist_key,
        artist_name,
        mbid,
        playcount,
        listeners,
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
        ORDER BY fetched_at DESC, lower(artist_name)
    ) = 1
),
ordered_snapshots AS (
    SELECT
        artist_key,
        artist_name,
        mbid,
        playcount,
        listeners,
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
)
SELECT
    metric.week_start,
    metric.canonical_genre,
    snapshot.artist_key,
    snapshot.artist_name,
    snapshot.mbid,
    snapshot.playcount - snapshot.previous_playcount,
    snapshot.listeners - snapshot.previous_listeners,
    (
        snapshot.playcount - snapshot.previous_playcount
        + 5 * (snapshot.listeners - snapshot.previous_listeners)
    ),
    snapshot.fetched_at
FROM mart_.genre_weekly AS metric
CROSS JOIN unnest(metric.listening_artist_keys) AS receipt(artist_key)
INNER JOIN ordered_snapshots AS snapshot
    ON
        snapshot.artist_key = receipt.artist_key
        AND CAST(date_trunc('week', snapshot.fetched_at) AS DATE)
            = metric.week_start
WHERE
    snapshot.previous_playcount IS NOT NULL
    AND snapshot.previous_listeners IS NOT NULL
    AND snapshot.playcount >= snapshot.previous_playcount
    AND snapshot.listeners >= snapshot.previous_listeners;

INSERT INTO mart_.supply_evidence (
    week_start,
    canonical_genre,
    release_group_mbid,
    title,
    artist_credits,
    first_release_date,
    types,
    genres
)
SELECT
    metric.week_start,
    metric.canonical_genre,
    release.release_group_mbid,
    release.title,
    release.artist_credits,
    CAST(release.first_release_date AS DATE),
    release.types,
    release.genres
FROM mart_.genre_weekly AS metric
CROSS JOIN unnest(
    metric.supply_release_group_mbids
) AS receipt(release_group_mbid)
INNER JOIN raw_.mb_release_groups AS release
    ON release.release_group_mbid = receipt.release_group_mbid
WHERE regexp_full_match(
    release.first_release_date,
    '[0-9]{4}-[0-9]{2}-[0-9]{2}'
);
