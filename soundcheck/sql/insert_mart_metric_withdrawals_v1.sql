INSERT INTO mart_.metric_row_withdrawals
SELECT
    'v1',
    'v1',
    ?,
    legacy.week_start,
    legacy.canonical_genre,
    legacy.opportunity,
    legacy.discovery_gap,
    'listening_window_not_valid_weekly'
FROM mart_.genre_weekly AS legacy
LEFT JOIN mart_.genre_weekly_versioned AS corrected
    ON corrected.derivation_version = ?
    AND corrected.week_start = legacy.week_start
    AND corrected.canonical_genre = legacy.canonical_genre
WHERE
    legacy.opportunity IS NOT NULL
    AND (corrected.opportunity IS NULL OR corrected.week_start IS NULL);
