SELECT canonical_genre
FROM mart_.genre_weekly_production
WHERE lower(canonical_genre) = lower(?)
LIMIT 1;
