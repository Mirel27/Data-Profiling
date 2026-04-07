-- SQLite reporting helpers for column value profiling.
-- Requires objects from 01_column_value_profiler.sql and data loaded by
-- scripts/run_sqlite_column_profile.py.

CREATE VIEW IF NOT EXISTS v_column_profile_latest_snapshot AS
SELECT
    p.table_name,
    p.column_name,
    p.unique_value,
    p.value_count,
    p.snapshot_date_time,
    p.profile_run_id
FROM column_value_profile p
WHERE p.snapshot_date_time = (
    SELECT MAX(snapshot_date_time)
    FROM column_value_profile
);

CREATE VIEW IF NOT EXISTS v_column_profile_latest_per_table AS
WITH latest AS (
    SELECT
        table_name,
        MAX(snapshot_date_time) AS max_snapshot
    FROM column_value_profile
    GROUP BY table_name
)
SELECT
    p.table_name,
    p.column_name,
    p.unique_value,
    p.value_count,
    p.snapshot_date_time,
    p.profile_run_id
FROM column_value_profile p
JOIN latest l
  ON l.table_name = p.table_name
 AND l.max_snapshot = p.snapshot_date_time;

-- Monitoring query for run status:
-- SELECT profile_run_id, status, started_at, finished_at, tables_profiled,
--        columns_profiled, rows_inserted, error_message
-- FROM column_profile_run_log
-- ORDER BY started_at DESC;
