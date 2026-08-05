SELECT
    release_group_mbid,
    first_release_date,
    artist_credits,
    genres,
    tags,
    fetched_at
FROM raw_.mb_release_groups
ORDER BY first_release_date, release_group_mbid;
