-- SQLite column value profiler DDL
-- Executed by scripts/run_sqlite_column_profile.py

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS column_value_profile (
    profile_run_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    unique_value TEXT,
    value_count INTEGER NOT NULL,
    snapshot_date_time TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_cvp_table_col_snap
    ON column_value_profile(table_name, column_name, snapshot_date_time);

CREATE INDEX IF NOT EXISTS idx_cvp_run
    ON column_value_profile(profile_run_id);

CREATE TABLE IF NOT EXISTS column_profile_run_log (
    profile_run_id TEXT PRIMARY KEY,
    db_path TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    table_filter TEXT,
    tables_profiled INTEGER NOT NULL DEFAULT 0,
    columns_profiled INTEGER NOT NULL DEFAULT 0,
    rows_inserted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

-- Latest snapshot query template:
-- SELECT table_name, column_name, unique_value, value_count AS count, snapshot_date_time
-- FROM column_value_profile
-- WHERE snapshot_date_time = (SELECT MAX(snapshot_date_time) FROM column_value_profile)
-- ORDER BY table_name, column_name, value_count DESC;
