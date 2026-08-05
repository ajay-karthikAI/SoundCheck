SET TimeZone = 'UTC';

WITH release_tags AS (
    SELECT
        release.release_group_mbid,
        release.first_release_date,
        trim(unnest(release.genres)) AS raw_tag,
        'musicbrainz_genre' AS source_system
    FROM raw_.mb_release_groups AS release

    UNION

    SELECT
        release.release_group_mbid,
        release.first_release_date,
        trim(source_tag.name) AS raw_tag,
        'musicbrainz_tag' AS source_system
    FROM
        raw_.mb_release_groups AS release,
        unnest(release.tags) AS expanded(source_tag)
),
release_genres AS (
    SELECT DISTINCT
        source.release_group_mbid,
        source.first_release_date,
        mapping.canonical_genre
    FROM release_tags AS source
    INNER JOIN stg_.tag_genre_map AS mapping
        ON
            mapping.source_system = source.source_system
            AND lower(trim(mapping.raw_tag)) = lower(source.raw_tag)
    WHERE
        source.raw_tag <> ''
        AND regexp_full_match(source.first_release_date, '[0-9]{4}-[0-9]{2}-[0-9]{2}')
)
SELECT
    CAST(
        date_trunc('week', CAST(first_release_date AS DATE))
        AS DATE
    ) AS week_start,
    canonical_genre,
    release_group_mbid
FROM release_genres
ORDER BY week_start, canonical_genre, release_group_mbid;
