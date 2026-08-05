WITH lastfm_tags AS (
    SELECT tag AS source_tag
    FROM raw_.lastfm_tag_snapshots

    UNION

    SELECT unnest(list_concat(tags, source_genres)) AS source_tag
    FROM raw_.lastfm_artist_snapshots
),
musicbrainz_genres AS (
    SELECT unnest(genres) AS source_tag
    FROM raw_.mb_release_groups
),
musicbrainz_tags AS (
    SELECT source_tag.name AS source_tag
    FROM
        raw_.mb_release_groups,
        unnest(tags) AS expanded(source_tag)
)
SELECT DISTINCT
    'lastfm' AS source_system,
    trim(source_tag) AS source_tag
FROM lastfm_tags
WHERE trim(source_tag) <> ''

UNION ALL

SELECT DISTINCT
    'musicbrainz_genre' AS source_system,
    trim(source_tag) AS source_tag
FROM musicbrainz_genres
WHERE trim(source_tag) <> ''

UNION ALL

SELECT DISTINCT
    'musicbrainz_tag' AS source_system,
    trim(source_tag) AS source_tag
FROM musicbrainz_tags
WHERE trim(source_tag) <> ''

ORDER BY source_system, source_tag;
