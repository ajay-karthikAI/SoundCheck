SELECT
    artist_name,
    mbid,
    listeners,
    playcount,
    tags,
    source_genres,
    fetched_at
FROM raw_.lastfm_artist_snapshots
ORDER BY fetched_at, lower(artist_name);
