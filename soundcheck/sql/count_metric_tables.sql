SELECT count(*)
FROM information_schema.tables
WHERE table_schema IN ('mart_', 'fcst_');

