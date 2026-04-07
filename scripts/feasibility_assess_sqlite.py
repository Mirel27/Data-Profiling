#!/usr/bin/env python3
"""
SQLite Feasibility Assessment Tool

Loads a data dictionary (CSV) and assesses feasibility of each data point against
a SQLite mock database. Computes a RAG (Red/Amber/Green) score based on:
  - Metadata match score (45%): how well does column name match the data point?
  - Population completeness (40%): what % of rows are non-null?
  - Distinctiveness (15%): log-scaled distinct value count

Output: CSV with feasibility scoring and recommendations.
"""

import argparse
import csv
import sqlite3
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ColumnMeta:
    table_name: str
    column_name: str
    data_type: str


@dataclass(frozen=True)
class DataPoint:
    request_id: str
    data_point_name: str
    domain: str
    description: str
    expected_table: Optional[str]
    expected_column: Optional[str]
    priority: str


@dataclass(frozen=True)
class FeasibilityResult:
    request_id: str
    data_point_name: str
    domain: str
    table_name: str
    column_name: str
    data_type: str
    row_count: int
    non_null_count: int
    populated_pct: float
    distinct_count: int
    metadata_match_score: float
    feasibility_score: float
    rag_score: str
    recommendation: str


# Keyword expansion for natural language matching
KEYWORD_MAP = {
    "age": ["age", "dob", "birth", "year_of_birth", "yob"],
    "gender": ["sex", "gender"],
    "smoke": ["smoking", "smoker", "tobacco"],
    "cancer": ["cancer", "tumor", "tumour", "oncology", "malignant", "stage", "diagnoses", "diagnosis"],
    "treatment": ["treatment", "therapy", "chemo", "radio", "immuno", "surgery", "regimen"],
    "death": ["mortality", "death", "deceased", "survival", "dod"],
    "comorbidity": ["charlson", "comorbid", "index"],
    "pathology": ["pathology", "specimens", "biopsy", "histology", "cytology", "molecular"],
}


def read_schema(db_path: str) -> dict[str, list[ColumnMeta]]:
    """Extract all table+column metadata from SQLite without scanning data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    schema = {}
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for (table_name,) in cursor.fetchall():
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = []
        for _cid, col_name, col_type, _notnull, _dflt_value, _pk in cursor.fetchall():
            columns.append(ColumnMeta(
                table_name=table_name,
                column_name=col_name,
                data_type=col_type or "TEXT"
            ))
        schema[table_name] = columns
    
    conn.close()
    return schema


def read_data_dictionary(dict_path: str) -> list[DataPoint]:
    """Load data dictionary from CSV."""
    data_points = []
    with open(dict_path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            data_points.append(DataPoint(
                request_id=row.get("request_id", ""),
                data_point_name=row.get("data_point_name", ""),
                domain=row.get("domain", ""),
                description=row.get("description", ""),
                expected_table=row.get("expected_table") or None,
                expected_column=row.get("expected_column") or None,
                priority=row.get("priority", ""),
            ))
    return data_points


def sample_column_stats(db_path: str, table_name: str, column_name: str) -> tuple[int, int, int]:
    """
    Get column statistics: (total_rows, non_null_count, distinct_count)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Total rows
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cursor.fetchone()[0]
        
        # Non-null count
        cursor.execute(f"SELECT COUNT({column_name}) FROM {table_name}")
        non_null_count = cursor.fetchone()[0]
        
        # Distinct count (with limit for large tables)
        cursor.execute(f"SELECT COUNT(DISTINCT {column_name}) FROM {table_name}")
        distinct_count = cursor.fetchone()[0]
        
        return total_rows, non_null_count, distinct_count
    except Exception as e:
        print(f"Warning: Failed to sample {table_name}.{column_name}: {e}")
        return 0, 0, 0
    finally:
        conn.close()


def tokenize(text: str) -> list[str]:
    """Extract tokens from text (lowercase, alphanumeric + underscore)."""
    return re.findall(r"[a-z0-9_]+", text.lower())


def expand_query(tokens: list[str]) -> set[str]:
    """Expand query tokens with keyword synonyms."""
    expanded = set(tokens)
    for token in tokens:
        for key, synonyms in KEYWORD_MAP.items():
            if token == key or token in synonyms:
                expanded.update(synonyms)
                expanded.add(key)
    return expanded


def score_column(col_name: str, description: str, query_tokens: set[str]) -> float:
    """
    Calculate metadata match score (0.0–1.0+).
    
    Scoring:
      - Exact token hits: +2.0 each
      - Fuzzy substring match: +0.0–1.0 range
    """
    col_tokens = set(tokenize(col_name)) | set(tokenize(description))
    exact_hits = len(query_tokens & col_tokens)
    fuzzy_score = max(
        (SequenceMatcher(None, q, c).ratio() for q in query_tokens for c in col_tokens if len(c) > 2),
        default=0.0,
    )
    return exact_hits * 2.0 + fuzzy_score


def compute_feasibility(
    metadata_score: float,
    populated_pct: float,
    distinct_count: int,
) -> tuple[float, str, str]:
    """
    Compute weighted feasibility score (0.0–1.0) and RAG flag.
    
    Weights:
      - Metadata match: 45%
      - Population completeness: 40%
      - Distinctiveness: 15% (log-scaled)
    """
    # Normalize inputs to [0, 1] range
    metadata_norm = min(metadata_score / 4.0, 1.0)  # Assume max ~4.0
    population_norm = min(populated_pct / 100.0, 1.0)
    distinct_norm = min(__import__("math").log(max(distinct_count + 1, 1)) / 8.0, 1.0)  # ln(x+1)/8
    
    feasibility = (
        0.45 * metadata_norm +
        0.40 * population_norm +
        0.15 * distinct_norm
    )
    
    # RAG classification
    if feasibility >= 0.75:
        rag = "GREEN"
        rec = "Feasible candidate. Prioritize in downstream extraction."
    elif feasibility >= 0.45:
        rag = "AMBER"
        rec = "Potentially feasible. Validate business rules and completeness."
    else:
        rag = "RED"
        rec = "Low feasibility. Consider alternative concept or additional source."
    
    return round(feasibility, 4), rag, rec


def assess_feasibility(
    db_path: str,
    dict_path: str,
    min_metadata_score: float = 0.8,
) -> list[FeasibilityResult]:
    """
    Main assessment pipeline:
    1. Load schema from SQLite database
    2. Load data dictionary
    3. Match data points against schema
    4. Sample column statistics from database
    5. Compute feasibility scores
    6. Return results sorted by score (descending)
    """
    print(f"[1/4] Reading SQLite schema from {db_path}...")
    schema = read_schema(db_path)
    print(f"      Found {len(schema)} tables")
    
    print(f"[2/4] Loading data dictionary from {dict_path}...")
    data_points = read_data_dictionary(dict_path)
    print(f"      Found {len(data_points)} data points")
    
    print(f"[3/4] Matching data points against schema...")
    results = []
    for dp in data_points:
        query_tokens = expand_query(tokenize(dp.data_point_name))
        
        # First pass: find candidate columns by metadata matching
        candidates = []
        for table_name, columns in schema.items():
            for col_meta in columns:
                score = score_column(col_meta.column_name, "", query_tokens)
                if score >= min_metadata_score:
                    candidates.append((table_name, col_meta, score))
        
        if not candidates:
            # No candidates found
            results.append(FeasibilityResult(
                request_id=dp.request_id,
                data_point_name=dp.data_point_name,
                domain=dp.domain,
                table_name="-",
                column_name="-",
                data_type="-",
                row_count=0,
                non_null_count=0,
                populated_pct=0.0,
                distinct_count=0,
                metadata_match_score=0.0,
                feasibility_score=0.0,
                rag_score="RED",
                recommendation="No matching columns in schema.",
            ))
            continue
        
        # Sort by metadata score descending and take top candidate
        candidates.sort(key=lambda x: x[2], reverse=True)
        table_name, col_meta, metadata_score = candidates[0]
        
        print(f"      [{dp.request_id}] {dp.data_point_name} → {table_name}.{col_meta.column_name}")
        
        # Sample statistics from database
        total_rows, non_null_count, distinct_count = sample_column_stats(
            db_path, table_name, col_meta.column_name
        )
        
        populated_pct = round((non_null_count / total_rows * 100.0) if total_rows > 0 else 0.0, 2)
        feasibility_score, rag, recommendation = compute_feasibility(
            metadata_score, populated_pct, distinct_count
        )
        
        results.append(FeasibilityResult(
            request_id=dp.request_id,
            data_point_name=dp.data_point_name,
            domain=dp.domain,
            table_name=table_name,
            column_name=col_meta.column_name,
            data_type=col_meta.data_type,
            row_count=total_rows,
            non_null_count=non_null_count,
            populated_pct=populated_pct,
            distinct_count=distinct_count,
            metadata_match_score=round(metadata_score, 4),
            feasibility_score=feasibility_score,
            rag_score=rag,
            recommendation=recommendation,
        ))
    
    # Sort by feasibility score descending
    results.sort(key=lambda r: r.feasibility_score, reverse=True)
    
    print(f"[4/4] Assessment complete. {len(results)} results.")
    
    # Summary stats
    green_count = sum(1 for r in results if r.rag_score == "GREEN")
    amber_count = sum(1 for r in results if r.rag_score == "AMBER")
    red_count = sum(1 for r in results if r.rag_score == "RED")
    print(f"\nSummary:")
    print(f"  GREEN:  {green_count}")
    print(f"  AMBER:  {amber_count}")
    print(f"  RED:    {red_count}")
    
    return results


def write_results(output_path: str, results: list[FeasibilityResult]) -> None:
    """Write results to CSV file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    header = [
        "request_id",
        "data_point_name",
        "domain",
        "table_name",
        "column_name",
        "data_type",
        "row_count",
        "non_null_count",
        "populated_pct",
        "distinct_count",
        "metadata_match_score",
        "feasibility_score",
        "rag_score",
        "recommendation",
    ]
    
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=header)
        writer.writeheader()
        for result in results:
            writer.writerow({
                "request_id": result.request_id,
                "data_point_name": result.data_point_name,
                "domain": result.domain,
                "table_name": result.table_name,
                "column_name": result.column_name,
                "data_type": result.data_type,
                "row_count": result.row_count,
                "non_null_count": result.non_null_count,
                "populated_pct": result.populated_pct,
                "distinct_count": result.distinct_count,
                "metadata_match_score": result.metadata_match_score,
                "feasibility_score": result.feasibility_score,
                "rag_score": result.rag_score,
                "recommendation": result.recommendation,
            })
    
    print(f"\n✓ Results written to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="SQLite Feasibility Assessment Tool",
        epilog="Example: %(prog)s --db data/dwh/mock_feasibility_sqlite.db --dict data/processed/mock_cancer_data_dictionary_50.csv --output data/processed/feasibility_assessment.csv"
    )
    parser.add_argument(
        "--db",
        type=str,
        required=True,
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--dict",
        type=str,
        required=True,
        help="Path to data dictionary CSV file",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/feasibility_assessment.csv",
        help="Output CSV file path (default: data/processed/feasibility_assessment.csv)",
    )
    parser.add_argument(
        "--min-metadata-score",
        type=float,
        default=0.8,
        help="Minimum metadata match score to consider a candidate (default: 0.8)",
    )
    
    args = parser.parse_args()
    
    # Run assessment
    results = assess_feasibility(
        db_path=args.db,
        dict_path=args.dict,
        min_metadata_score=args.min_metadata_score,
    )
    
    # Write results
    write_results(args.output, results)


if __name__ == "__main__":
    main()
