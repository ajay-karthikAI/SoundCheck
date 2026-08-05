SELECT
    artist_name,
    mbid
FROM raw_.lastfm_artist_snapshots
QUALIFY row_number() OVER (
    PARTITION BY lower(artist_name)
    ORDER BY
        (mbid IS NOT NULL) DESC,
        fetched_at DESC
) = 1
ORDER BY lower(artist_name);

