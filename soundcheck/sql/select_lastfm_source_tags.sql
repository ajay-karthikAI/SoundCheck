WITH source_tags AS (
    SELECT tag AS raw_tag
    FROM raw_.lastfm_tag_snapshots

    UNION

    SELECT unnest(tags) AS raw_tag
    FROM raw_.lastfm_artist_snapshots
)
SELECT DISTINCT
    'lastfm' AS source_system,
    trim(raw_tag) AS raw_tag
FROM source_tags
WHERE trim(raw_tag) <> '';

