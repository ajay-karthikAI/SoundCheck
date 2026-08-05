SELECT column_name
FROM information_schema.columns
WHERE
    table_schema = 'stg_'
    AND table_name = 'tag_genre_map_v2'
ORDER BY ordinal_position;
