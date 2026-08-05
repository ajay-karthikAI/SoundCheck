WITH credits AS (
    SELECT
        release.fetched_at,
        release.genres,
        release.tags,
        credit.artist_name,
        credit.mbid
    FROM
        raw_.mb_release_groups AS release,
        unnest(release.artist_credits) AS expanded_credit(credit)
),
genre_evidence AS (
    SELECT
        artist_name,
        mbid,
        'musicbrainz_genre' AS source_system,
        trim(unnest(genres)) AS source_tag,
        fetched_at
    FROM credits
),
tag_evidence AS (
    SELECT
        artist_name,
        mbid,
        'musicbrainz_tag' AS source_system,
        trim(source_tag.name) AS source_tag,
        fetched_at
    FROM
        credits,
        unnest(tags) AS expanded_tag(source_tag)
)
SELECT DISTINCT *
FROM (
    SELECT * FROM genre_evidence
    UNION ALL
    SELECT * FROM tag_evidence
)
WHERE source_tag <> ''
ORDER BY lower(artist_name), source_system, lower(source_tag);
