WITH predictions AS (
    SELECT
        artist_key,
        list(
            canonical_genre_id
            ORDER BY membership_weight DESC, canonical_genre_id
        ) AS predicted_genre_ids
    FROM stg_.artist_genre_memberships_v2
    WHERE taxonomy_version = ?
    GROUP BY artist_key
),
representative AS (
    SELECT *
    FROM stg_.artist_genre_memberships_v2
    WHERE taxonomy_version = ?
    QUALIFY row_number() OVER (
        PARTITION BY artist_key
        ORDER BY membership_weight DESC, canonical_genre_id
    ) = 1
),
latest_listening AS (
    SELECT
        coalesce(
            'mbid:' || nullif(lower(mbid), ''),
            'name:' || lower(trim(artist_name))
        ) AS artist_key,
        listeners
    FROM raw_.lastfm_artist_snapshots
    QUALIFY row_number() OVER (
        PARTITION BY coalesce(
            nullif(lower(mbid), ''),
            lower(trim(artist_name))
        )
        ORDER BY fetched_at DESC
    ) = 1
)
SELECT
    representative.artist_key,
    representative.artist_name,
    representative.source_systems[1] AS source_system,
    representative.source_tags[1] AS source_tag,
    predictions.predicted_genre_ids,
    representative.method,
    representative.macro_family_id,
    coalesce(mapping.language, 'und') AS language,
    representative.artist_key_type,
    latest_listening.listeners
FROM representative
JOIN predictions USING (artist_key)
LEFT JOIN stg_.tag_genre_map_v2 AS mapping
    ON mapping.taxonomy_version = representative.taxonomy_version
    AND mapping.source_system = representative.source_systems[1]
    AND mapping.canonical_genre_id = representative.canonical_genre_id
    AND lower(trim(mapping.source_tag)) = lower(
        trim(representative.source_tags[1])
    )
LEFT JOIN latest_listening USING (artist_key)
ORDER BY
    representative.macro_family_id,
    language,
    source_system,
    representative.method,
    representative.artist_key_type,
    representative.artist_key;
