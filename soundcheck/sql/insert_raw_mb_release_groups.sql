INSERT INTO raw_.mb_release_groups (
    release_group_mbid,
    title,
    artist_credits,
    artist_mbids,
    first_release_date,
    types,
    genres,
    tags,
    fetched_at
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (release_group_mbid) DO NOTHING;

