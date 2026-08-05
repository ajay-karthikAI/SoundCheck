SELECT DISTINCT
    'musicbrainz_genre' AS source_system,
    trim(unnest(genres)) AS raw_tag
FROM raw_.mb_release_groups

UNION

SELECT DISTINCT
    'musicbrainz_tag' AS source_system,
    trim(source_tag.name) AS raw_tag
FROM
    raw_.mb_release_groups,
    unnest(tags) AS expanded(source_tag)
WHERE trim(source_tag.name) <> '';

