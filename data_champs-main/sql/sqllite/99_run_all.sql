-- SQLite CLI helper script.
-- Usage:
--   sqlite3 data/dwh/raw_demo.db ".read sql/sqllite/99_run_all.sql"

.read sql/sqllite/01_column_value_profiler.sql
.read sql/sqllite/02_orchestration.sql

-- Example output reads:
SELECT profile_run_id, status, started_at, finished_at, tables_profiled, columns_profiled, rows_inserted
FROM column_profile_run_log
ORDER BY started_at DESC
LIMIT 20;

SELECT table_name, column_name, unique_value, value_count, snapshot_date_time
FROM v_column_profile_latest_snapshot
ORDER BY table_name, column_name, value_count DESC
LIMIT 200;
