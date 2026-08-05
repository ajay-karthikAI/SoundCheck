SELECT
    release_group_mbid,
    title,
    artist_credits,
    artist_mbids,
    first_release_date,
    types,
    genres,
    tags,
    fetched_at
FROM raw_.mb_release_groups
ORDER BY release_group_mbid;

