#!/usr/bin/env python3
"""Profile every table/column in a SQLite database into column_value_profile.

This script:
- Executes SQL setup scripts from sql/sqllite (in filename order)
- Enumerates all user tables and columns
- Runs one-column-at-a-time aggregation:
    SELECT COALESCE(CAST(col AS TEXT), ?) AS unique_value, COUNT(*)
    FROM table
    GROUP BY COALESCE(CAST(col AS TEXT), ?)
- Inserts results into column_value_profile with a run snapshot timestamp

Usage example:
  python scripts/run_sqlite_column_profile.py \
        --db data/dwh/raw_demo.db

Run:

/Users/macbookpro/Documents/_dev2/data_champs/.venv/bin/python /Users/macbookpro/Documents/_dev2/data_champs/scripts/run_sqlite_column_profile.py --db data/dwh/raw_demo.db


Check:

-- Table
SELECT * FROM raw_cancer_registry_0001


SELECT registry_source, COUNT(*) FROM raw_cancer_registry_0001
GROUP BY registry_source

SELECT dq_status, COUNT(*) FROM raw_cancer_registry_0001
GROUP BY dq_status


SELECT COUNT(*) FROM column_value_profile

SELECT profile_run_id, table_name, column_name, unique_value, value_count, snapshot_date_time, created_at
FROM column_value_profile
WHERE table_name = 'raw_cancer_registry_0001' 
AND column_name  = 'registry_source'
AND snapshot_date_time  = (SELECT MAX(snapshot_date_time) FROM column_value_profile WHERE table_name = 'raw_cancer_registry_0001' 
AND column_name  = 'registry_source')



SELECT profile_run_id, table_name, column_name, unique_value, value_count, snapshot_date_time, created_at
FROM column_value_profile
WHERE table_name = 'raw_genomic_variants' 
AND column_name  = 'registry_source'
AND snapshot_date_time  = (SELECT MAX(snapshot_date_time) FROM column_value_profile WHERE table_name = 'raw_cancer_registry_0001' 
AND column_name  = 'registry_source')


"""

from __future__ import annotations

import argparse
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

DEFAULT_SQL_DIR = Path("sql/sqllite")
INTERNAL_TABLES = {"column_value_profile", "column_profile_run_log"}


@dataclass(frozen=True)
class ColumnRef:
    table_name: str
    column_name: str


def q_ident(name: str) -> str:
    """Quote SQLite identifier safely."""
    return '"' + name.replace('"', '""') + '"'


def apply_schema_sql(conn: sqlite3.Connection, sql_file: Path) -> None:
    sql_text = sql_file.read_text(encoding="utf-8")
    conn.executescript(sql_text)


def list_sql_scripts(sql_dir: Path) -> list[Path]:
    """Return executable SQL files in deterministic order.

    Excludes helper scripts intended for sqlite3 CLI (e.g. 99_run_all.sql with .read).
    """
    scripts: list[Path] = []
    for candidate in sorted(sql_dir.glob("*.sql")):
        name = candidate.name.lower()
        if name.startswith("99_") or "run_all" in name:
            continue
        scripts.append(candidate)
    return scripts


def resolve_sql_scripts(sql_dir: Path, sql_files: list[str]) -> list[Path]:
    resolved: list[Path] = []

    if sql_dir.exists():
        resolved.extend(list_sql_scripts(sql_dir))

    for sql_file in sql_files:
        path = Path(sql_file).resolve()
        if not path.exists():
            raise FileNotFoundError(f"SQL file not found: {path}")
        if path not in resolved:
            resolved.append(path)

    if not resolved:
        raise FileNotFoundError(
            f"No executable SQL scripts found in {sql_dir} and no valid --sql-file supplied"
        )

    return resolved


def list_target_tables(conn: sqlite3.Connection, table_like: str | None) -> list[str]:
    query = """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
    """
    rows = conn.execute(query).fetchall()
    tables = [r[0] for r in rows if r[0] not in INTERNAL_TABLES]

    if table_like:
        pattern = table_like.lower().replace("%", "")
        tables = [t for t in tables if pattern in t.lower()]

    return tables


def list_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    pragma_sql = f"PRAGMA table_info({q_ident(table_name)})"
    rows = conn.execute(pragma_sql).fetchall()
    return [row[1] for row in rows]


def iter_table_columns(conn: sqlite3.Connection, tables: Iterable[str]) -> Iterable[ColumnRef]:
    for table_name in tables:
        for column_name in list_columns(conn, table_name):
            yield ColumnRef(table_name=table_name, column_name=column_name)


def insert_profile_for_column(
    conn: sqlite3.Connection,
    profile_run_id: str,
    snapshot_ts: str,
    null_label: str,
    ref: ColumnRef,
) -> int:
    """Run one-column aggregation and insert into column_value_profile."""
    table_sql = q_ident(ref.table_name)
    col_sql = q_ident(ref.column_name)

    insert_sql = f"""
        INSERT INTO column_value_profile (
            profile_run_id,
            table_name,
            column_name,
            unique_value,
            value_count,
            snapshot_date_time
        )
        SELECT
            ?,
            ?,
            ?,
            COALESCE(CAST({col_sql} AS TEXT), ?) AS unique_value,
            COUNT(*) AS value_count,
            ?
        FROM {table_sql}
        GROUP BY COALESCE(CAST({col_sql} AS TEXT), ?)
    """

    cur = conn.execute(
        insert_sql,
        (
            profile_run_id,
            ref.table_name,
            ref.column_name,
            null_label,
            snapshot_ts,
            null_label,
        ),
    )
    return int(cur.rowcount or 0)


def init_run_log(
    conn: sqlite3.Connection,
    profile_run_id: str,
    db_path: str,
    started_at: str,
    table_filter: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO column_profile_run_log (
            profile_run_id,
            db_path,
            started_at,
            status,
            table_filter
        )
        VALUES (?, ?, ?, 'RUNNING', ?)
        """,
        (profile_run_id, db_path, started_at, table_filter),
    )


def complete_run_log(
    conn: sqlite3.Connection,
    profile_run_id: str,
    status: str,
    finished_at: str,
    tables_profiled: int,
    columns_profiled: int,
    rows_inserted: int,
    error_message: str | None,
) -> None:
    conn.execute(
        """
        UPDATE column_profile_run_log
        SET finished_at = ?,
            status = ?,
            tables_profiled = ?,
            columns_profiled = ?,
            rows_inserted = ?,
            error_message = ?
        WHERE profile_run_id = ?
        """,
        (
            finished_at,
            status,
            tables_profiled,
            columns_profiled,
            rows_inserted,
            error_message,
            profile_run_id,
        ),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SQLite column value profiling.")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument(
        "--sql-file",
        action="append",
        default=[],
        help="Optional SQL file to execute in addition to scripts found under --sql-dir",
    )
    parser.add_argument(
        "--sql-dir",
        default=str(DEFAULT_SQL_DIR),
        help="Directory containing SQL setup scripts to execute in filename order",
    )
    parser.add_argument(
        "--table-like",
        default=None,
        help="Optional case-insensitive substring filter for table names",
    )
    parser.add_argument(
        "--null-label",
        default="<NULL>",
        help="Label used for NULL values in profile output",
    )
    parser.add_argument(
        "--clear-latest-for-table",
        action="store_true",
        help="Delete existing profile rows for each table before inserting this run",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).resolve()
    sql_dir = Path(args.sql_dir).resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    sql_scripts = resolve_sql_scripts(sql_dir=sql_dir, sql_files=args.sql_file)

    profile_run_id = str(uuid.uuid4())
    snapshot_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    started_at = snapshot_ts

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")

    tables_profiled = 0
    columns_profiled = 0
    rows_inserted = 0

    try:
        with conn:
            for sql_script in sql_scripts:
                apply_schema_sql(conn, sql_script)
            init_run_log(conn, profile_run_id, str(db_path), started_at, args.table_like)

        target_tables = list_target_tables(conn, args.table_like)
        if not target_tables:
            with conn:
                complete_run_log(
                    conn,
                    profile_run_id,
                    "SUCCESS",
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                    0,
                    0,
                    0,
                    None,
                )
            print("No matching tables found. Nothing profiled.")
            return 0

        with conn:
            for table_name in target_tables:
                if args.clear_latest_for_table:
                    conn.execute(
                        "DELETE FROM column_value_profile WHERE table_name = ?",
                        (table_name,),
                    )

                table_had_columns = False
                for ref in iter_table_columns(conn, [table_name]):
                    table_had_columns = True
                    inserted = insert_profile_for_column(
                        conn,
                        profile_run_id=profile_run_id,
                        snapshot_ts=snapshot_ts,
                        null_label=args.null_label,
                        ref=ref,
                    )
                    columns_profiled += 1
                    rows_inserted += inserted

                if table_had_columns:
                    tables_profiled += 1

            complete_run_log(
                conn,
                profile_run_id,
                "SUCCESS",
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                tables_profiled,
                columns_profiled,
                rows_inserted,
                None,
            )

        print(f"Profile run completed: {profile_run_id}")
        print(f"Snapshot timestamp: {snapshot_ts}")
        print(f"Tables profiled: {tables_profiled}")
        print(f"Columns profiled: {columns_profiled}")
        print(f"Rows inserted into column_value_profile: {rows_inserted}")
        print("SQL scripts executed:")
        for script in sql_scripts:
            print(f"- {script}")
        print(
            "Query latest results: SELECT table_name, column_name, unique_value, value_count, snapshot_date_time "
            "FROM column_value_profile WHERE snapshot_date_time = (SELECT MAX(snapshot_date_time) FROM column_value_profile);"
        )
        return 0

    except Exception as exc:
        with conn:
            complete_run_log(
                conn,
                profile_run_id,
                "FAILED",
                datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                tables_profiled,
                columns_profiled,
                rows_inserted,
                str(exc),
            )
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
