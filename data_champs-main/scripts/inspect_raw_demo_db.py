#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect the generated raw_demo SQLite source database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/dwh/raw_demo.db"),
        help="Path to the SQLite database to inspect.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    try:
        raw_tables = [
            row[0]
            for row in cur.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table' AND name GLOB 'raw_*'
                ORDER BY name
                """
            ).fetchall()
        ]

        print(f"Database: {args.db}")
        print(f"Raw tables: {len(raw_tables)}")
        print()
        print("First 20 raw tables:")
        for table_name in raw_tables[:20]:
            print(f"  - {table_name}")

        if not raw_tables:
            print()
            print("No raw tables found in this database.")
            return 1

        print()
        print("Sample patients:")
        for row in cur.execute(
            """
            SELECT patient_sk, pseudo_nhs_id, sex
            FROM raw_cancer_patients
            ORDER BY patient_sk
            LIMIT 10
            """
        ).fetchall():
            print(f"  - {row}")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
