SELECT
    (SELECT count(*) FROM stg_.post_artist_links) AS link_count,
    (SELECT count(*) FROM stg_.post_artist_ambiguities) AS ambiguity_count,
    (
        SELECT count(*)
        FROM stg_.post_artist_resolution_attempts
    ) AS attempt_count;

