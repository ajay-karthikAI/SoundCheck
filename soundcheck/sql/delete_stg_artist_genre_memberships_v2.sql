DELETE FROM stg_.artist_genre_memberships_v2
WHERE taxonomy_version = ?
  AND artist_key = ?;
