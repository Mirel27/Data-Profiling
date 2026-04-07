#!/usr/bin/env python3
"""Generate an RBAC-aware Excel report from PySpark tables.

Output columns:
- model_name
- table_name
- row_count
- populated_pct
- access_status
- top_5_values
- suggestion
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable

from openpyxl import Workbook
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


@dataclass(frozen=True)
class TableRule:
    model_name: str
    database_name: str
    table_name: str
    path: str
    fmt: str
    value_column: str
    full_access_roles: tuple[str, ...]
    allow_anonymous: bool = False


RESTRICTED_IDENTIFIER_COLUMNS = {"subject", "encntr_id", "episode_id"}
ALLOWED_DATABASE_NAME = "icht_prod"


def load_dataframe(spark: SparkSession, rule: TableRule) -> DataFrame:
    reader = spark.read.format(rule.fmt)
    if rule.fmt.lower() == "csv":
        reader = reader.option("header", "true").option("inferSchema", "true")
    return reader.load(rule.path)


def anonymized_value_expr(column_name: str):
    # Hash raw values so anon output is irreversible while preserving frequency grouping.
    return F.concat(F.lit("anon_"), F.substring(F.sha2(F.col(column_name).cast("string"), 256), 1, 10))


def fetch_top_values(df: DataFrame, value_column: str, anonymize: bool) -> list[str]:
    if value_column not in df.columns:
        return ["column_not_found"]

    value_expr = anonymized_value_expr(value_column) if anonymize else F.col(value_column).cast("string")
    ranked = (
        df.where(F.col(value_column).isNotNull())
        .select(value_expr.alias("value"))
        .groupBy("value")
        .count()
        .orderBy(F.desc("count"), F.asc("value"))
        .limit(5)
    )
    return [f"{row['value']} (n={row['count']})" for row in ranked.collect()]


def suggest_action(access_status: str, rule: TableRule, role: str) -> str:
    if access_status == "POLICY_BLOCKED":
        return (
            "Blocked by governance policy. Do not request identifier columns "
            "(subject, encntr_id, episode_id). Use non-identifying aggregated fields instead."
        )
    if access_status == "DATABASE_BLOCKED":
        return (
            f"Blocked by governance policy. Queries are allowed only on database '{ALLOWED_DATABASE_NAME}'. "
            f"Current table points to '{rule.database_name}'."
        )
    if access_status == "FULL_ACCESS":
        return "Access granted. Continue normal analysis."
    if access_status == "ANON_ONLY":
        return (
            "Anonymized access only. Request full table permission if record-level values are needed."
        )
    return (
        f"Permission required. Request role mapping for '{role}' to table '{rule.table_name}' "
        f"in model '{rule.model_name}'."
    )


def iter_report_rows(
    spark: SparkSession,
    rules: Iterable[TableRule],
    role: str,
    anon_access_all_models: bool,
) -> Generator[list[object], None, None]:
    for rule in rules:
        if rule.database_name != ALLOWED_DATABASE_NAME:
            yield [
                rule.model_name,
                rule.table_name,
                0,
                0.0,
                "DATABASE_BLOCKED",
                "restricted_database",
                suggest_action("DATABASE_BLOCKED", rule, role),
            ]
            continue

        if rule.value_column in RESTRICTED_IDENTIFIER_COLUMNS:
            yield [
                rule.model_name,
                rule.table_name,
                0,
                0.0,
                "POLICY_BLOCKED",
                "restricted_identifier_column",
                suggest_action("POLICY_BLOCKED", rule, role),
            ]
            continue

        df = load_dataframe(spark, rule)

        row_count = df.count()
        if rule.value_column in df.columns and row_count > 0:
            populated_count = df.where(F.col(rule.value_column).isNotNull()).count()
            populated_pct = round((populated_count / row_count) * 100.0, 2)
        else:
            populated_pct = 0.0

        has_full_access = role in rule.full_access_roles
        has_anon_access = rule.allow_anonymous or anon_access_all_models

        if has_full_access:
            access_status = "FULL_ACCESS"
            top_values = fetch_top_values(df, rule.value_column, anonymize=False)
        elif has_anon_access:
            access_status = "ANON_ONLY"
            top_values = fetch_top_values(df, rule.value_column, anonymize=True)
        else:
            access_status = "NO_ACCESS"
            top_values = ["access_denied"]

        suggestion = suggest_action(access_status, rule, role)
        yield [
            rule.model_name,
            rule.table_name,
            row_count,
            populated_pct,
            access_status,
            "; ".join(top_values),
            suggestion,
        ]


def write_excel(output_path: Path, rows: Iterable[list[object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("rbac_table_report")
    sheet.append(
        [
            "model_name",
            "table_name",
            "row_count",
            "populated_pct",
            "access_status",
            "top_5_values",
            "suggestion",
        ]
    )

    for row in rows:
        sheet.append(row)

    workbook.save(output_path)


def write_csv(output_path: Path, rows: Iterable[list[object]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "model_name",
        "table_name",
        "row_count",
        "populated_pct",
        "access_status",
        "top_5_values",
        "suggestion",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def write_report(output_path: Path, rows: Iterable[list[object]]) -> None:
    suffix = output_path.suffix.lower()
    if suffix == ".csv":
        write_csv(output_path, rows)
        return
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm", ""}:
        write_excel(output_path, rows)
        return
    raise ValueError("Unsupported output format. Use .xlsx or .csv")


def parse_config(config_path: Path) -> tuple[bool, list[TableRule]]:
    with config_path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    anon_access_all_models = bool(raw.get("anon_access_all_models", False))
    table_rules = [
        TableRule(
            model_name=item["model_name"],
            database_name=item.get("database_name", ALLOWED_DATABASE_NAME),
            table_name=item["table_name"],
            path=item["path"],
            fmt=item.get("format", "csv"),
            value_column=item["value_column"],
            full_access_roles=tuple(item.get("full_access_roles", [])),
            allow_anonymous=bool(item.get("allow_anonymous", False)),
        )
        for item in raw.get("tables", [])
    ]
    return anon_access_all_models, table_rules


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create RBAC-based table access Excel report via PySpark")
    parser.add_argument("--config", type=Path, required=True, help="Path to JSON config")
    parser.add_argument("--role", type=str, required=True, help="User role to evaluate")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/rbac_table_report.xlsx"),
        help="Output path (.xlsx or .csv)",
    )
    parser.add_argument("--app-name", type=str, default="rbac-excel-report")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    anon_access_all_models, rules = parse_config(args.config)
    if not rules:
        raise ValueError("No table rules found in config")

    spark = SparkSession.builder.appName(args.app_name).getOrCreate()
    try:
        rows = iter_report_rows(
            spark=spark,
            rules=rules,
            role=args.role,
            anon_access_all_models=anon_access_all_models,
        )
        write_report(args.output, rows)
        print(f"RBAC report written to: {args.output}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
