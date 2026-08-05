SELECT 'raw_' AS source_area, 'bluesky_engagement' AS table_name,
       count(*) AS row_count,
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), '')) AS fingerprint
FROM raw_.bluesky_engagement AS row_data
UNION ALL
SELECT 'raw_', 'bluesky_posts', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM raw_.bluesky_posts AS row_data
UNION ALL
SELECT 'raw_', 'lastfm_artist_snapshots', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM raw_.lastfm_artist_snapshots AS row_data
UNION ALL
SELECT 'raw_', 'lastfm_tag_snapshots', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM raw_.lastfm_tag_snapshots AS row_data
UNION ALL
SELECT 'raw_', 'mb_release_groups', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM raw_.mb_release_groups AS row_data
UNION ALL
SELECT 'stg_', 'canonical_genre_embeddings', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM stg_.canonical_genre_embeddings AS row_data
UNION ALL
SELECT 'stg_', 'post_artist_ambiguities', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM stg_.post_artist_ambiguities AS row_data
UNION ALL
SELECT 'stg_', 'post_artist_links', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM stg_.post_artist_links AS row_data
UNION ALL
SELECT 'stg_', 'post_artist_resolution_attempts', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM stg_.post_artist_resolution_attempts AS row_data
UNION ALL
SELECT 'stg_', 'tag_genre_map', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM stg_.tag_genre_map AS row_data
UNION ALL
SELECT 'mart_', 'bluesky_music_feed', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.bluesky_music_feed AS row_data
UNION ALL
SELECT 'mart_', 'briefs', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.briefs AS row_data
UNION ALL
SELECT 'mart_', 'conversation_evidence', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.conversation_evidence AS row_data
UNION ALL
SELECT 'mart_', 'ecosystem_weekly', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.ecosystem_weekly AS row_data
UNION ALL
SELECT 'mart_', 'genre_weekly', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.genre_weekly AS row_data
UNION ALL
SELECT 'mart_', 'listening_evidence', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.listening_evidence AS row_data
UNION ALL
SELECT 'mart_', 'scene_map', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.scene_map AS row_data
UNION ALL
SELECT 'mart_', 'supply_evidence', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM mart_.supply_evidence AS row_data
UNION ALL
SELECT 'fcst_', 'backtest_ledger', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM fcst_.backtest_ledger AS row_data
UNION ALL
SELECT 'fcst_', 'model_scores', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM fcst_.model_scores AS row_data
UNION ALL
SELECT 'fcst_', 'next_up', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM fcst_.next_up AS row_data
UNION ALL
SELECT 'fcst_', 'predictions', count(*),
       md5(coalesce(string_agg(to_json(row_data), '' ORDER BY to_json(row_data)), ''))
FROM fcst_.predictions AS row_data
ORDER BY source_area, table_name;
