SET TimeZone = 'UTC';

WITH credit_memberships AS (
    SELECT
        release.release_group_mbid,
        release.first_release_date,
        release.title,
        release.artist_credits,
        release.types,
        release.genres,
        release.fetched_at,
        membership.canonical_genre_id,
        membership.macro_family_id,
        max(membership.membership_weight) AS unnormalized_weight
    FROM
        raw_.mb_release_groups AS release,
        unnest(release.artist_credits) AS expanded(credit)
    JOIN stg_.artist_genre_memberships_v2 AS membership
        ON membership.taxonomy_version = ?
        AND (
            lower(membership.artist_mbid) = lower(credit.mbid)
            OR (
                nullif(credit.mbid, '') IS NULL
                AND lower(trim(membership.artist_name))
                    = lower(trim(credit.artist_name))
            )
        )
    WHERE regexp_full_match(
        release.first_release_date,
        '[0-9]{4}-[0-9]{2}-[0-9]{2}'
    )
    AND try_cast(release.first_release_date AS DATE) IS NOT NULL
    GROUP BY
        release.release_group_mbid,
        release.first_release_date,
        release.title,
        release.artist_credits,
        release.types,
        release.genres,
        release.fetched_at,
        membership.canonical_genre_id,
        membership.macro_family_id
),
normalized AS (
    SELECT
        *,
        unnormalized_weight
            / sum(unnormalized_weight) OVER (
                PARTITION BY release_group_mbid
            ) AS membership_weight
    FROM credit_memberships
)
SELECT
    CAST(
        date_trunc('week', try_cast(first_release_date AS DATE))
        AS DATE
    ) AS week_start,
    canonical_genre_id,
    macro_family_id,
    release_group_mbid,
    membership_weight,
    title,
    artist_credits,
    CAST(first_release_date AS DATE),
    types,
    genres,
    fetched_at
FROM normalized
ORDER BY week_start, canonical_genre_id, release_group_mbid;
