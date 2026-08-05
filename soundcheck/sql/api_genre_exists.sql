SELECT canonical_genre
FROM mart_.genre_weekly
WHERE lower(canonical_genre) = lower(?)
LIMIT 1;
