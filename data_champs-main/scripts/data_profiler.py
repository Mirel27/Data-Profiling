#!/usr/bin/env python3
"""RBAC-aware data profiling tool with quality color-coding and natural language search.

Two modes:
  profile  - Column-level quality report per table.
  search   - Describe what you need in plain English; matched against accessible models only.

Output columns (profile mode):
  model_name, table_name, column_name, data_type, row_count,
  non_null_count, populated_pct, distinct_count, quality_flag,
  sample_values, suggestion

quality_flag color codes:
  GREEN  - populated_pct >= 90
  AMBER  - populated_pct >= 50
  RED    - populated_pct < 50
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Generator, Iterable

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


# ---------------------------------------------------------------------------
# Policy constants (same as rbac_excel_report.py)
# ---------------------------------------------------------------------------

RESTRICTED_IDENTIFIER_COLUMNS = {"subject", "encntr_id", "episode_id"}
ALLOWED_DATABASE_NAME = "icht_prod"

ROLES_WITH_SAMPLE_ACCESS = {"data_engineer", "admin"}

# Tables to exclude from profiling output (metadata tables, not source data)
EXCLUDED_TABLE_NAMES = {"data_profile"}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableDef:
    model_name: str
    database_name: str
    table_name: str
    path: str
    fmt: str
    full_access_roles: tuple[str, ...]
    profile_access_roles: tuple[str, ...]
    column_descriptions: dict[str, str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_dataframe(spark: SparkSession, table: TableDef) -> DataFrame:
    if table.fmt.lower() == "sqlite":
        db_path = str(Path(table.path).resolve())
        url = f"jdbc:sqlite:{db_path}"
        return (
            spark.read.format("jdbc")
            .option("url", url)
            .option("dbtable", table.table_name)
            .option("driver", "org.sqlite.JDBC")
            .load()
        )
    reader = spark.read.format(table.fmt)
    if table.fmt.lower() == "csv":
        reader = reader.option("header", "true").option("inferSchema", "true")
    return reader.load(table.path)


def quality_flag(populated_pct: float) -> str:
    if populated_pct >= 90.0:
        return "GREEN"
    if populated_pct >= 50.0:
        return "AMBER"
    return "RED"


def fetch_sample_values(df: DataFrame, column: str, limit: int = 5) -> list[str]:
    rows = (
        df.where(F.col(column).isNotNull())
        .select(F.col(column).cast("string").alias("v"))
        .distinct()
        .limit(limit)
        .collect()
    )
    return [r["v"] for r in rows]


# ---------------------------------------------------------------------------
# Profile generator  (lazy, yielded row-by-row)
# ---------------------------------------------------------------------------


def iter_profile_rows(
    spark: SparkSession,
    tables: Iterable[TableDef],
    role: str,
) -> Generator[list[object], None, None]:
    """Yield one row per column per table."""
    can_see_samples = role in ROLES_WITH_SAMPLE_ACCESS

    for table in tables:
        # Skip metadata tables (e.g. data_profile itself)
        if table.table_name in EXCLUDED_TABLE_NAMES:
            continue

        # Database policy guard
        if table.database_name != ALLOWED_DATABASE_NAME:
            yield [
                table.model_name,
                table.table_name,
                "*",
                "",
                0,
                0,
                0.0,
                0,
                "BLOCKED",
                "",
                f"Database '{table.database_name}' not allowed. Only '{ALLOWED_DATABASE_NAME}' permitted.",
            ]
            continue

        # Access check: full_access or profile-only access
        has_full_access = role in table.full_access_roles
        has_profile_access = role in table.profile_access_roles
        if not has_full_access and not has_profile_access:
            yield [
                table.model_name,
                table.table_name,
                "*",
                "",
                0,
                0,
                0.0,
                0,
                "NO_ACCESS",
                "",
                f"Role '{role}' does not have access to this table. Request permission.",
            ]
            continue

        df = load_dataframe(spark, table)
        total_rows = df.count()

        for field in df.schema.fields:
            col_name = field.name

            # Restricted identifier guard
            if col_name.lower() in RESTRICTED_IDENTIFIER_COLUMNS:
                yield [
                    table.model_name,
                    table.table_name,
                    col_name,
                    str(field.dataType.simpleString()),
                    total_rows,
                    0,
                    0.0,
                    0,
                    "BLOCKED",
                    "",
                    "Restricted identifier column. Do not query.",
                ]
                continue

            non_null = df.where(F.col(col_name).isNotNull()).count()
            pop_pct = round((non_null / total_rows) * 100.0, 2) if total_rows > 0 else 0.0
            distinct = df.select(col_name).distinct().count()
            flag = quality_flag(pop_pct)

            if can_see_samples and has_full_access:
                samples = "; ".join(fetch_sample_values(df, col_name))
            else:
                samples = ""

            suggestion = ""
            if flag == "RED":
                suggestion = "Low population. Verify data pipeline or consider excluding."
            elif flag == "AMBER":
                suggestion = "Moderate population. Review for completeness."

            yield [
                table.model_name,
                table.table_name,
                col_name,
                str(field.dataType.simpleString()),
                total_rows,
                non_null,
                pop_pct,
                distinct,
                flag,
                samples,
                suggestion,
            ]


# ---------------------------------------------------------------------------
# Natural-language column search (keyword + fuzzy match)
# ---------------------------------------------------------------------------

# Maps common layman phrases to likely column-name tokens.
KEYWORD_MAP: dict[str, list[str]] = {
    "age": ["age", "dob", "birth"],
    "gender": ["sex", "gender"],
    "smoke": ["smoking", "smoker", "tobacco"],
    "cancer": ["cancer", "tumor", "tumour", "oncology", "malignant", "stage"],
    "treatment": ["treatment", "therapy", "chemo", "radio", "immuno", "surgery"],
    "death": ["mortality", "death", "deceased", "survival"],
    "blood": ["wbc", "hemoglobin", "hb", "platelet", "crp"],
    "weight": ["bmi", "weight", "obesity"],
    "hospital": ["admit", "discharge", "encounter", "episode", "inpatient", "outpatient"],
    "family": ["family", "hereditary", "genetic"],
    "identifier": ["patient_id", "id", "mrn"],
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _expand_query(tokens: list[str]) -> set[str]:
    expanded: set[str] = set(tokens)
    for token in tokens:
        for key, synonyms in KEYWORD_MAP.items():
            if token == key or token in synonyms:
                expanded.update(synonyms)
                expanded.add(key)
    return expanded


def _score_column(col_name: str, col_desc: str, query_tokens: set[str]) -> float:
    col_tokens = set(_tokenize(col_name)) | set(_tokenize(col_desc))
    exact_hits = len(query_tokens & col_tokens)
    fuzzy_score = max(
        (SequenceMatcher(None, q, c).ratio() for q in query_tokens for c in col_tokens),
        default=0.0,
    )
    return exact_hits * 2.0 + fuzzy_score


def iter_search_rows(
    spark: SparkSession,
    tables: Iterable[TableDef],
    role: str,
    query: str,
    min_score: float = 0.5,
) -> Generator[list[object], None, None]:
    """Yield matching columns from accessible models for a natural language query."""
    tokens = _tokenize(query)
    expanded = _expand_query(tokens)

    for table in tables:
        if table.database_name != ALLOWED_DATABASE_NAME:
            continue
        if role not in table.full_access_roles and role not in table.profile_access_roles:
            continue

        df = load_dataframe(spark, table)
        total_rows = df.count()

        for field in df.schema.fields:
            col_name = field.name
            if col_name.lower() in RESTRICTED_IDENTIFIER_COLUMNS:
                continue

            col_desc = table.column_descriptions.get(col_name, "")
            score = _score_column(col_name, col_desc, expanded)
            if score < min_score:
                continue

            non_null = df.where(F.col(col_name).isNotNull()).count()
            pop_pct = round((non_null / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

            yield [
                table.model_name,
                table.table_name,
                col_name,
                str(field.dataType.simpleString()),
                total_rows,
                non_null,
                pop_pct,
                round(score, 2),
                col_desc or "(no description)",
            ]


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

PROFILE_HEADER = [
    "model_name",
    "table_name",
    "column_name",
    "data_type",
    "row_count",
    "non_null_count",
    "populated_pct",
    "distinct_count",
    "quality_flag",
    "sample_values",
    "suggestion",
]

SEARCH_HEADER = [
    "model_name",
    "table_name",
    "column_name",
    "data_type",
    "row_count",
    "non_null_count",
    "populated_pct",
    "relevance_score",
    "description",
]

ASSESS_HEADER = [
    "model_name",
    "table_name",
    "data_point",
    "matched_column",
    "data_type",
    "relevance_score",
    "access_status",
    "row_count",
    "non_null_count",
    "populated_pct",
    "feasibility_flag",
    "notes",
]


def write_csv(output_path: Path, header: list[str], rows: Iterable[list[object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def materialize_to_sqlite(
    db_path: Path,
    table_name: str,
    header: list[str],
    rows: Iterable[list[object]],
) -> int:
    """Write profile rows into a SQLite table, replacing any previous data."""
    col_defs = ", ".join(f'"{h}" TEXT' for h in header)
    placeholders = ", ".join("?" for _ in header)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
        conn.execute(f'CREATE TABLE "{table_name}" ({col_defs})')
        count = 0
        for row in rows:
            conn.execute(
                f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                [str(v) for v in row],
            )
            count += 1
        conn.commit()
        return count
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Config parser
# ---------------------------------------------------------------------------


def parse_config(config_path: Path) -> list[TableDef]:
    with config_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    return [
        TableDef(
            model_name=item["model_name"],
            database_name=item.get("database_name", ALLOWED_DATABASE_NAME),
            table_name=item["table_name"],
            path=item["path"],
            fmt=item.get("format", "csv"),
            full_access_roles=tuple(item.get("full_access_roles", [])),
            profile_access_roles=tuple(item.get("profile_access_roles", [])),
            column_descriptions=item.get("column_descriptions", {}),
        )
        for item in raw.get("tables", [])
    ]


# ---------------------------------------------------------------------------
# Feasibility assessment for many tables (metadata-first)
# ---------------------------------------------------------------------------


def _parse_data_points(raw_points: str) -> list[str]:
    points = [p.strip() for p in re.split(r"[,;\n]+", raw_points) if p.strip()]
    if not points:
        raise ValueError("No data points provided. Use --data-points with comma-separated values.")
    return points


def _feasibility_flag(populated_pct: float | None) -> str:
    if populated_pct is None:
        return "UNKNOWN"
    if populated_pct >= 90.0:
        return "HIGH"
    if populated_pct >= 50.0:
        return "MEDIUM"
    return "LOW"


def iter_assessment_rows(
    spark: SparkSession,
    tables: Iterable[TableDef],
    role: str,
    data_points: list[str],
    min_score: float = 1.2,
    max_cols_per_table: int = 8,
    metadata_only: bool = False,
) -> Generator[list[object], None, None]:
    """Yield data-point feasibility rows.

    Designed for large table counts: it uses cheap metadata matching first, and only
    computes population metrics for matched columns (single aggregate pass per table).
    """
    point_tokens: dict[str, set[str]] = {
        point: _expand_query(_tokenize(point)) for point in data_points
    }

    for table in tables:
        if table.database_name != ALLOWED_DATABASE_NAME:
            for point in data_points:
                yield [
                    table.model_name,
                    table.table_name,
                    point,
                    "",
                    "",
                    0.0,
                    "BLOCKED",
                    0,
                    0,
                    0.0,
                    "UNKNOWN",
                    f"Database '{table.database_name}' not allowed. Only '{ALLOWED_DATABASE_NAME}' permitted.",
                ]
            continue

        has_access = role in table.full_access_roles or role in table.profile_access_roles
        access_status = "ACCESS_GRANTED" if has_access else "NO_ACCESS"

        df = load_dataframe(spark, table)

        candidates: list[dict[str, object]] = []
        for field in df.schema.fields:
            col_name = field.name
            if col_name.lower() in RESTRICTED_IDENTIFIER_COLUMNS:
                continue

            col_desc = table.column_descriptions.get(col_name, "")
            for point, tokens in point_tokens.items():
                score = _score_column(col_name, col_desc, tokens)
                if score < min_score:
                    continue
                candidates.append(
                    {
                        "data_point": point,
                        "column_name": col_name,
                        "data_type": str(field.dataType.simpleString()),
                        "score": round(score, 2),
                    }
                )

        if not candidates:
            for point in data_points:
                yield [
                    table.model_name,
                    table.table_name,
                    point,
                    "",
                    "",
                    0.0,
                    access_status,
                    "" if metadata_only else 0,
                    "" if metadata_only else 0,
                    "" if metadata_only else 0.0,
                    "UNKNOWN",
                    "No sufficiently relevant columns found in this table.",
                ]
            continue

        candidates = sorted(candidates, key=lambda c: float(c["score"]), reverse=True)[:max_cols_per_table]

        total_rows: int | None = None
        non_null_counts: dict[str, int] = {}
        if not metadata_only and has_access:
            total_rows = df.count()

            selected_cols = sorted({str(c["column_name"]) for c in candidates})
            alias_map = {col_name: f"c{i}" for i, col_name in enumerate(selected_cols)}
            agg_exprs = [
                F.sum(F.when(F.col(col_name).isNotNull(), 1).otherwise(0)).alias(alias)
                for col_name, alias in alias_map.items()
            ]
            if agg_exprs:
                counts = df.agg(*agg_exprs).collect()[0].asDict()
                non_null_counts = {col_name: int(counts.get(alias, 0) or 0) for col_name, alias in alias_map.items()}

        for cand in candidates:
            col_name = str(cand["column_name"])
            non_null = non_null_counts.get(col_name) if non_null_counts else None
            pct: float | None = None
            if total_rows is not None and non_null is not None:
                pct = round((non_null / total_rows) * 100.0, 2) if total_rows > 0 else 0.0

            yield [
                table.model_name,
                table.table_name,
                cand["data_point"],
                col_name,
                cand["data_type"],
                cand["score"],
                access_status,
                total_rows if total_rows is not None else "",
                non_null if non_null is not None else "",
                pct if pct is not None else "",
                _feasibility_flag(pct),
                "Metadata-only match." if metadata_only else "",
            ]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="RBAC-aware data profiling and natural-language column search"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # -- profile sub-command --
    p_prof = sub.add_parser("profile", help="Generate column-level quality profile")
    p_prof.add_argument("--config", type=Path, required=True)
    p_prof.add_argument("--role", type=str, required=True, help="Viewer role (e.g. data_engineer, researcher)")
    p_prof.add_argument("--output", type=Path, default=Path("data/processed/data_profile.csv"))
    p_prof.add_argument("--app-name", type=str, default="data-profiler")

    # -- search sub-command --
    p_search = sub.add_parser("search", help="Search columns with a plain-English description")
    p_search.add_argument("--config", type=Path, required=True)
    p_search.add_argument("--role", type=str, required=True)
    p_search.add_argument("--query", type=str, required=True, help="What you are looking for in plain English")
    p_search.add_argument("--output", type=Path, default=Path("data/processed/search_results.csv"))
    p_search.add_argument("--app-name", type=str, default="data-profiler-search")

    # -- materialize sub-command --
    p_mat = sub.add_parser("materialize", help="Compute full profile and store it in the SQLite database")
    p_mat.add_argument("--config", type=Path, required=True)
    p_mat.add_argument("--db", type=Path, default=Path("data/dwh/raw_demo.db"),
                       help="SQLite database to write the data_profile table into")
    p_mat.add_argument("--table", type=str, default="data_profile",
                       help="Name of the materialized profile table")
    p_mat.add_argument("--app-name", type=str, default="data-profiler-materialize")

    # -- assess sub-command --
    p_assess = sub.add_parser(
        "assess",
        help="Fast feasibility assessment for requested data points across many tables",
    )
    p_assess.add_argument("--config", type=Path, required=True)
    p_assess.add_argument("--role", type=str, required=True)
    p_assess.add_argument(
        "--data-points",
        type=str,
        required=True,
        help="Comma-separated requested data points, e.g. 'smoking status, treatment response, survival'",
    )
    p_assess.add_argument(
        "--min-score",
        type=float,
        default=1.2,
        help="Minimum relevance score to keep a column match",
    )
    p_assess.add_argument(
        "--max-cols-per-table",
        type=int,
        default=8,
        help="Max matched columns emitted per table",
    )
    p_assess.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip row-level stats and return schema/description matches only",
    )
    p_assess.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/feasibility_assessment.csv"),
    )
    p_assess.add_argument("--app-name", type=str, default="data-profiler-assess")

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tables = parse_config(args.config)
    if not tables:
        raise ValueError("No tables found in config")

    spark = SparkSession.builder.appName(args.app_name).getOrCreate()
    try:
        if args.command == "profile":
            rows = iter_profile_rows(spark, tables, args.role)
            write_csv(args.output, PROFILE_HEADER, rows)
            print(f"Profile report written to: {args.output}")

        elif args.command == "search":
            rows = iter_search_rows(spark, tables, args.role, args.query)
            write_csv(args.output, SEARCH_HEADER, rows)
            print(f"Search results written to: {args.output}")

        elif args.command == "materialize":
            # Always profile at data_engineer level to capture full detail
            rows = iter_profile_rows(spark, tables, role="data_engineer")
            count = materialize_to_sqlite(args.db, args.table, PROFILE_HEADER, rows)
            print(f"Materialized {count} rows into '{args.table}' table in {args.db}")

        elif args.command == "assess":
            data_points = _parse_data_points(args.data_points)
            rows = iter_assessment_rows(
                spark,
                tables,
                args.role,
                data_points,
                min_score=args.min_score,
                max_cols_per_table=args.max_cols_per_table,
                metadata_only=args.metadata_only,
            )
            write_csv(args.output, ASSESS_HEADER, rows)
            print(f"Feasibility assessment written to: {args.output}")

        elif args.command == "materialize":
            # Always profile at data_engineer level to capture full detail
            rows = iter_profile_rows(spark, tables, role="data_engineer")
            count = materialize_to_sqlite(args.db, args.table, PROFILE_HEADER, rows)
            print(f"Materialized {count} rows into '{args.table}' table in {args.db}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
