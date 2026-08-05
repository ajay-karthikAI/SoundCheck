SET TimeZone = 'UTC';

WITH weekly_snapshots AS (
    SELECT
        artist_name,
        nullif(mbid, '') AS mbid,
        playcount,
        listeners,
        fetched_at
    FROM raw_.lastfm_artist_snapshots
    QUALIFY row_number() OVER (
        PARTITION BY
            coalesce(nullif(lower(mbid), ''), lower(trim(artist_name))),
            CAST(date_trunc('week', fetched_at) AS DATE)
        ORDER BY fetched_at DESC
    ) = 1
),
ordered_snapshots AS (
    SELECT
        artist_name,
        mbid,
        playcount,
        listeners,
        fetched_at,
        lag(playcount) OVER (
            PARTITION BY coalesce(nullif(lower(mbid), ''), lower(trim(artist_name)))
            ORDER BY fetched_at
        ) AS previous_playcount,
        lag(listeners) OVER (
            PARTITION BY coalesce(nullif(lower(mbid), ''), lower(trim(artist_name)))
            ORDER BY fetched_at
        ) AS previous_listeners,
        lag(fetched_at) OVER (
            PARTITION BY coalesce(nullif(lower(mbid), ''), lower(trim(artist_name)))
            ORDER BY fetched_at
        ) AS previous_fetched_at
    FROM weekly_snapshots
)
SELECT
    CAST(date_trunc('week', snapshot.fetched_at) AS DATE) AS week_start,
    membership.canonical_genre_id,
    membership.macro_family_id,
    membership.artist_key,
    membership.membership_weight,
    snapshot.playcount,
    snapshot.listeners,
    snapshot.previous_playcount,
    snapshot.previous_listeners,
    snapshot.artist_name,
    snapshot.mbid,
    snapshot.fetched_at,
    snapshot.previous_fetched_at,
    membership.method,
    membership.confidence
FROM ordered_snapshots AS snapshot
JOIN stg_.artist_genre_memberships_v2 AS membership
    ON membership.taxonomy_version = ?
    AND (
        (
            snapshot.mbid IS NOT NULL
            AND lower(membership.artist_mbid) = lower(snapshot.mbid)
        )
        OR (
            snapshot.mbid IS NULL
            AND lower(trim(membership.artist_name))
                = lower(trim(snapshot.artist_name))
        )
    )
ORDER BY week_start, membership.canonical_genre_id, membership.artist_key;
