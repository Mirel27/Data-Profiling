#!/usr/bin/env python3
"""Streamlit UI for researchers to explore data profiles and ask questions.

Run:
    make setup
    .venv/bin/python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Generator, Iterable

import numpy as np
import pandas as pd
import streamlit as st


def ensure_java_runtime() -> None:
    """Point PySpark at a compatible Java install (preferring Java 17/21).

    Java 25 removed Subject.getSubject() with no compat path; we must avoid it.
    Priority order:
      1. Repo-local JDK (.tools/java/jdk-17)
      2. Codespace-managed Java 21 (/home/codespace/java/21.0.9-ms)
      3. Codespace-managed Java 21 via 'current' symlink (only if ≤ Java 21)
      4. macOS java_home -v 17
    """
    # If JAVA_HOME is already set and points to a safe version (≤21), honour it.
    existing = os.environ.get("JAVA_HOME", "")
    if existing:
        java_bin = Path(existing) / "bin" / "java"
        if java_bin.exists():
            try:
                result = subprocess.run(
                    [str(java_bin), "-version"],
                    capture_output=True, text=True, check=False,
                )
                version_line = (result.stderr or result.stdout).splitlines()[0]
                # Extract major version number, e.g. "25" from '25.0.1'
                import re as _re
                m = _re.search(r'version "(?:1\.)?(\d+)', version_line)
                if m and int(m.group(1)) <= 21:
                    return  # safe version, keep it
                # Otherwise fall through to override with a safe one
            except Exception:
                return  # can't probe, trust it

    project_root = Path(__file__).resolve().parents[2]
    candidates = [
        # Repo-local Java 17
        project_root / ".tools" / "java" / "jdk-17" / "Contents" / "Home",
        project_root / ".tools" / "java" / "jdk-17",
        # Codespace Java 21
        Path("/home/codespace/java/21.0.9-ms"),
        Path("/home/codespace/java/21.0.10-ms"),
    ]

    for candidate in candidates:
        java_bin = candidate / "bin" / "java"
        if java_bin.exists():
            os.environ["JAVA_HOME"] = str(candidate)
            os.environ["PATH"] = f"{candidate / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
            return

    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/libexec/java_home", "-v", "17"],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return
        java_home = result.stdout.strip()
        if java_home:
            os.environ["JAVA_HOME"] = java_home
            os.environ["PATH"] = f"{Path(java_home) / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"


ensure_java_runtime()

# Java 18–21 removed the legacy Subject.getSubject(AccessControlContext) API
# unless this thread-local flag is set. Must be in JAVA_TOOL_OPTIONS so it
# reaches the JVM before Hadoop's UserGroupInformation initialises.
_existing_jtool = os.environ.get("JAVA_TOOL_OPTIONS", "")
if "-Djdk.security.auth.subject.useTL=true" not in _existing_jtool:
    os.environ["JAVA_TOOL_OPTIONS"] = (
        f"{_existing_jtool} -Djdk.security.auth.subject.useTL=true".strip()
    )

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

RESTRICTED_IDENTIFIER_COLUMNS = {"subject", "encntr_id", "episode_id"}
ALLOWED_DATABASE_NAME = "icht_prod"
ROLES_WITH_SAMPLE_ACCESS = {"data_engineer", "admin"}

FLAG_COLORS = {
    "GREEN": "#27ae60",
    "AMBER": "#f39c12",
    "RED": "#e74c3c",
    "BLOCKED": "#95a5a6",
    "NO_ACCESS": "#7f8c8d",
}

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
# Description inference helpers
# ---------------------------------------------------------------------------

# Common clinical/data abbreviations used in raw column names.
ABBREVIATION_MAP: dict[str, str] = {
    "yob": "year of birth",
    "dob": "date of birth",
    "reg": "registration",
    "dx": "diagnosis",
    "tx": "treatment",
    "adm": "admission",
    "dis": "discharge",
    "los": "length of stay",
    "cons": "consultant",
    "proc": "procedure",
    "opcs4": "OPCS-4",
    "icd10": "ICD-10",
    "mdt": "multidisciplinary team",
    "os": "overall survival",
    "pfs": "progression-free survival",
    "ea": "emergency admission",
    "vte": "venous thromboembolism",
    "px": "prophylaxis",
    "dt": "date/time",
    "hr": "heart rate",
    "sbp": "systolic blood pressure",
    "rr": "respiratory rate",
    "news2": "NEWS2 score",
    "wcc": "white cell count",
    "plt": "platelet count",
    "cr": "creatinine",
    "alb": "albumin",
    "tmb": "tumour mutational burden",
    "msi": "microsatellite instability",
    "gy": "gray",
}


def _friendly_phrase_from_column(col_name: str) -> str:
    """Convert terse technical column names into a readable phrase."""
    tokens = [t for t in re.split(r"[_\W]+", col_name.lower()) if t]
    if not tokens:
        return col_name

    expanded: list[str] = []
    for t in tokens:
        expanded.append(ABBREVIATION_MAP.get(t, t))

    phrase = " ".join(expanded)
    phrase = re.sub(r"\s+", " ", phrase).strip()
    return phrase


def infer_column_description(col_name: str, data_type: str | None = None) -> str:
    """Generate a fallback description for columns missing config metadata."""
    base = _friendly_phrase_from_column(col_name)
    c = col_name.lower()

    # Structural suffix hints improve consistency for synthetic schemas.
    if c.endswith("_sk"):
        desc = f"{base} surrogate key"
    elif c.endswith("_id"):
        desc = f"{base} identifier"
    elif c.endswith("_dt") or c.endswith("_date"):
        desc = f"{base} date"
    elif c.endswith("_flag"):
        desc = f"{base} indicator"
    elif c.endswith("_code"):
        desc = f"{base} code"
    elif c.endswith("_pct"):
        desc = f"{base} percentage"
    elif c.endswith("_count"):
        desc = f"{base} count"
    elif c.endswith("_days"):
        desc = f"{base} in days"
    elif c.endswith("_mg"):
        desc = f"{base} in milligrams"
    elif c.endswith("_gy"):
        desc = f"{base} in Gray"
    else:
        desc = base

    desc = desc[0].upper() + desc[1:] if desc else col_name
    if data_type:
        # Keep this concise; used in UI and search context text.
        desc = f"{desc} ({data_type})"
    return desc


# ---------------------------------------------------------------------------
# Spark helpers
# ---------------------------------------------------------------------------


@st.cache_resource
def get_spark() -> SparkSession:
    java17_opts = (
        "--add-opens=java.base/javax.security.auth=ALL-UNNAMED "
        "--add-opens=java.base/java.lang=ALL-UNNAMED "
        "--add-opens=java.base/java.nio=ALL-UNNAMED "
        "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED "
        "--add-opens=java.base/java.io=ALL-UNNAMED "
        "--add-opens=java.base/java.util=ALL-UNNAMED "
        "-Djdk.security.auth.subject.useTL=true"
    )
    return (
        SparkSession.builder.appName("researcher-ui")
        .config("spark.driver.extraJavaOptions", java17_opts)
        .config("spark.executor.extraJavaOptions", java17_opts)
        .getOrCreate()
    )


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
# Materialized profile reader
# ---------------------------------------------------------------------------

PROFILE_TABLE = "data_profile"


def load_materialized_profile(
    db_path: Path,
    tables: list[TableDef],
    role: str,
) -> pd.DataFrame | None:
    """Try to read the pre-computed data_profile table from SQLite.

    Returns a role-filtered DataFrame, or None if the table does not exist.
    """
    db_file = Path(db_path).resolve()
    if not db_file.exists():
        return None

    conn = sqlite3.connect(str(db_file))
    try:
        # Check the table exists
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (PROFILE_TABLE,),
        )
        if cur.fetchone() is None:
            return None

        df = pd.read_sql_query(f'SELECT * FROM "{PROFILE_TABLE}"', conn)
    finally:
        conn.close()

    if df.empty:
        return None

    # Cast numeric columns back from TEXT
    for col in ("row_count", "non_null_count", "distinct_count"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    if "populated_pct" in df.columns:
        df["populated_pct"] = pd.to_numeric(df["populated_pct"], errors="coerce").fillna(0.0)

    # Rename to match UI column names
    df = df.rename(columns={
        "model_name": "model",
        "table_name": "table",
        "column_name": "column",
        "row_count": "rows_total",
        "non_null_count": "non_null",
        "distinct_count": "distinct",
        "quality_flag": "quality",
        "sample_values": "samples",
    })

    # Exclude the data_profile metadata table itself
    df = df[df["table"] != PROFILE_TABLE]

    # Apply RBAC: keep only tables the role can access
    accessible_tables = {
        t.table_name
        for t in tables
        if role in t.full_access_roles or role in t.profile_access_roles
    }
    df = df[df["table"].isin(accessible_tables)]

    # Suppress sample values for roles without sample access
    if role not in ROLES_WITH_SAMPLE_ACCESS:
        df["samples"] = ""

    # Add description column from config
    desc_map: dict[tuple[str, str], str] = {}
    for t in tables:
        for col_name, desc in t.column_descriptions.items():
            desc_map[(t.table_name, col_name)] = desc
    df["description"] = df.apply(
        lambda r: (
            desc_map.get((r["table"], r["column"]), "")
            or infer_column_description(r["column"], str(r.get("data_type", "") or ""))
        ),
        axis=1,
    )

    return df


def _save_profile_to_sqlite(db_path: Path, df: pd.DataFrame) -> None:
    """Write a build_profile() DataFrame into the data_profile SQLite table."""
    # Map UI column names back to the materialized schema
    col_map = {
        "model": "model_name", "table": "table_name", "column": "column_name",
        "rows_total": "row_count", "non_null": "non_null_count",
        "distinct": "distinct_count", "quality": "quality_flag",
        "samples": "sample_values",
    }
    out = df.rename(columns=col_map)
    keep = [
        "model_name", "table_name", "column_name", "data_type",
        "row_count", "non_null_count", "populated_pct", "distinct_count",
        "quality_flag", "sample_values", "suggestion",
    ]
    out = out[[c for c in keep if c in out.columns]]

    conn = sqlite3.connect(str(Path(db_path).resolve()))
    try:
        conn.execute(f'DROP TABLE IF EXISTS "{PROFILE_TABLE}"')
        out.to_sql(PROFILE_TABLE, conn, index=False, if_exists="replace")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Profile generator
# ---------------------------------------------------------------------------


def build_profile(
    spark: SparkSession,
    tables: list[TableDef],
    role: str,
) -> pd.DataFrame:
    can_see_samples = role in ROLES_WITH_SAMPLE_ACCESS
    rows: list[dict] = []

    for table in tables:
        if table.database_name != ALLOWED_DATABASE_NAME:
            rows.append(
                dict(
                    model=table.model_name,
                    table=table.table_name,
                    column="*",
                    data_type="",
                    rows_total=0,
                    non_null=0,
                    populated_pct=0.0,
                    distinct=0,
                    quality="BLOCKED",
                    samples="",
                    description="",
                    suggestion=f"Database '{table.database_name}' not allowed.",
                )
            )
            continue

        has_full = role in table.full_access_roles
        has_profile = role in table.profile_access_roles
        if not has_full and not has_profile:
            rows.append(
                dict(
                    model=table.model_name,
                    table=table.table_name,
                    column="*",
                    data_type="",
                    rows_total=0,
                    non_null=0,
                    populated_pct=0.0,
                    distinct=0,
                    quality="NO_ACCESS",
                    samples="",
                    description="",
                    suggestion=f"Role '{role}' has no access. Request permission.",
                )
            )
            continue

        df = load_dataframe(spark, table)
        total = df.count()

        for field in df.schema.fields:
            col_name = field.name
            col_desc = table.column_descriptions.get(col_name, "") or infer_column_description(
                col_name,
                field.dataType.simpleString(),
            )

            if col_name.lower() in RESTRICTED_IDENTIFIER_COLUMNS:
                rows.append(
                    dict(
                        model=table.model_name,
                        table=table.table_name,
                        column=col_name,
                        data_type=field.dataType.simpleString(),
                        rows_total=total,
                        non_null=0,
                        populated_pct=0.0,
                        distinct=0,
                        quality="BLOCKED",
                        samples="",
                        description=col_desc,
                        suggestion="Restricted identifier. Do not query.",
                    )
                )
                continue

            nn = df.where(F.col(col_name).isNotNull()).count()
            pct = round((nn / total) * 100.0, 2) if total > 0 else 0.0
            dist = df.select(col_name).distinct().count()
            flag = quality_flag(pct)

            samples = ""
            if can_see_samples and has_full:
                samples = "; ".join(fetch_sample_values(df, col_name))

            suggestion = ""
            if flag == "RED":
                suggestion = "Low population. Verify pipeline or exclude."
            elif flag == "AMBER":
                suggestion = "Moderate population. Review completeness."

            rows.append(
                dict(
                    model=table.model_name,
                    table=table.table_name,
                    column=col_name,
                    data_type=field.dataType.simpleString(),
                    rows_total=total,
                    non_null=nn,
                    populated_pct=pct,
                    distinct=dist,
                    quality=flag,
                    samples=samples,
                    description=col_desc,
                    suggestion=suggestion,
                )
            )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# NL search
# ---------------------------------------------------------------------------

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


def _expand(tokens: list[str]) -> set[str]:
    out: set[str] = set(tokens)
    for t in tokens:
        for k, syns in KEYWORD_MAP.items():
            if t == k or t in syns:
                out.update(syns)
                out.add(k)
    return out


def _score(col_name: str, col_desc: str, q: set[str]) -> float:
    ct = set(_tokenize(col_name)) | set(_tokenize(col_desc))
    exact = len(q & ct)
    fuzzy = max((SequenceMatcher(None, a, b).ratio() for a in q for b in ct), default=0.0)
    return exact * 2.0 + fuzzy


def search_columns(
    db_path: Path,
    tables: list[TableDef],
    role: str,
    query: str,
    min_score: float = 1.5,
    top_n: int = 10,
) -> pd.DataFrame:
    """Search ALL tables via the materialized data_profile table but flag access status per result."""
    tokens = _tokenize(query)
    expanded = _expand(tokens)

    # Read materialized profile
    db_file = Path(db_path).resolve()
    conn = sqlite3.connect(str(db_file))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (PROFILE_TABLE,),
        )
        if cur.fetchone() is None:
            return pd.DataFrame()
        profile_df = pd.read_sql_query(f'SELECT * FROM "{PROFILE_TABLE}"', conn)
    finally:
        conn.close()

    if profile_df.empty:
        return pd.DataFrame()

    # Exclude the data_profile metadata table itself
    profile_df = profile_df[profile_df["table_name"] != PROFILE_TABLE]

    # Cast numerics
    for col in ("row_count", "non_null_count"):
        profile_df[col] = pd.to_numeric(profile_df[col], errors="coerce").fillna(0).astype(int)
    profile_df["populated_pct"] = pd.to_numeric(profile_df["populated_pct"], errors="coerce").fillna(0.0)

    # Build lookup of accessible tables and column descriptions
    access_map: dict[str, bool] = {}
    desc_map: dict[tuple[str, str], str] = {}
    for t in tables:
        has = role in t.full_access_roles or role in t.profile_access_roles
        access_map[t.table_name] = has
        for cn, desc in t.column_descriptions.items():
            desc_map[(t.table_name, cn)] = desc

    # Filter: skip restricted columns
    restricted = {c.lower() for c in RESTRICTED_IDENTIFIER_COLUMNS}

    rows: list[dict] = []
    for _, r in profile_df.iterrows():
        cn = r["column_name"]
        tbl = r["table_name"]
        if cn.lower() in restricted:
            continue
        desc = desc_map.get((tbl, cn), "") or infer_column_description(
            cn,
            str(r.get("data_type", "") or ""),
        )
        sc = _score(cn, desc, expanded)
        if sc < min_score:
            continue

        has_access = access_map.get(tbl, False)
        access = "ACCESS_GRANTED" if has_access else "NO_ACCESS \u2014 request permission"
        rows.append(dict(
            model=r["model_name"], table=tbl, column=cn,
            access_status=access,
            data_type=r["data_type"],
            rows_total=r["row_count"],
            non_null=r["non_null_count"],
            populated_pct=r["populated_pct"],
            quality=r.get("quality_flag", ""),
            relevance=round(sc, 2),
            description=desc or "(no description)",
        ))

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("relevance", ascending=False).head(top_n)
    return result


# ---------------------------------------------------------------------------
# Semantic (LLM) search
# ---------------------------------------------------------------------------

SEMANTIC_MODEL_NAME = "all-MiniLM-L6-v2"


@st.cache_resource
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(SEMANTIC_MODEL_NAME)


def _build_column_texts(
    profile_df: pd.DataFrame,
    desc_map: dict[tuple[str, str], str],
) -> list[str]:
    """Build a natural-language sentence for each column to embed."""
    texts: list[str] = []
    for _, r in profile_df.iterrows():
        tbl = r["table_name"]
        cn = r["column_name"]
        desc = desc_map.get((tbl, cn), "") or infer_column_description(
            cn,
            str(r.get("data_type", "") or ""),
        )
        # e.g. "raw_cancer_patients.smoking_status: Smoking history (never, former, current)"
        text = f"{tbl}.{cn}"
        if desc:
            text += f": {desc}"
        texts.append(text)
    return texts


def search_columns_semantic(
    db_path: Path,
    tables: list[TableDef],
    role: str,
    query: str,
    min_score: float = 0.25,
    top_n: int = 10,
) -> pd.DataFrame:
    """Semantic search using sentence-transformer embeddings."""
    # Read materialized profile
    db_file = Path(db_path).resolve()
    conn = sqlite3.connect(str(db_file))
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (PROFILE_TABLE,),
        )
        if cur.fetchone() is None:
            return pd.DataFrame()
        profile_df = pd.read_sql_query(f'SELECT * FROM "{PROFILE_TABLE}"', conn)
    finally:
        conn.close()

    if profile_df.empty:
        return pd.DataFrame()

    profile_df = profile_df[profile_df["table_name"] != PROFILE_TABLE]

    for col in ("row_count", "non_null_count"):
        profile_df[col] = pd.to_numeric(profile_df[col], errors="coerce").fillna(0).astype(int)
    profile_df["populated_pct"] = pd.to_numeric(profile_df["populated_pct"], errors="coerce").fillna(0.0)

    access_map: dict[str, bool] = {}
    desc_map: dict[tuple[str, str], str] = {}
    for t in tables:
        access_map[t.table_name] = role in t.full_access_roles or role in t.profile_access_roles
        for cn, desc in t.column_descriptions.items():
            desc_map[(t.table_name, cn)] = desc

    restricted = {c.lower() for c in RESTRICTED_IDENTIFIER_COLUMNS}
    mask = ~profile_df["column_name"].str.lower().isin(restricted)
    profile_df = profile_df[mask].reset_index(drop=True)

    if profile_df.empty:
        return pd.DataFrame()

    # Embed columns and query
    model = get_embedding_model()
    col_texts = _build_column_texts(profile_df, desc_map)
    col_embeddings = model.encode(col_texts, normalize_embeddings=True)
    query_embedding = model.encode(query, normalize_embeddings=True)

    # Cosine similarity (embeddings are normalized, so dot product = cosine)
    similarities = col_embeddings @ query_embedding

    # Hybrid scoring: boost semantic similarity with keyword overlap.
    # We weight each matching token by how *specific* it is — a token that
    # appears in many columns (like "date") gets a low weight, while a rare
    # token (like "birth") gets a high weight.  This keeps results on-topic.
    query_tokens = set(_tokenize(query))
    expanded_tokens = _expand(list(query_tokens))

    # Count how many columns each token appears in (inverse document frequency)
    all_col_token_sets = []
    for _, r in profile_df.iterrows():
        cn = r["column_name"]
        desc = desc_map.get((r["table_name"], cn), "")
        all_col_token_sets.append(set(_tokenize(cn)) | set(_tokenize(desc)))
    n_cols = len(all_col_token_sets)
    token_doc_freq: dict[str, int] = {}
    for tok in expanded_tokens:
        token_doc_freq[tok] = sum(1 for cts in all_col_token_sets if tok in cts)

    rows: list[dict] = []
    for idx, sim in enumerate(similarities):
        r = profile_df.iloc[idx]
        tbl = r["table_name"]
        cn = r["column_name"]
        desc = desc_map.get((tbl, cn), "") or infer_column_description(
            cn,
            str(r.get("data_type", "") or ""),
        )

        # Weighted keyword bonus: rare tokens count more
        col_tokens = all_col_token_sets[idx]
        matched = expanded_tokens & col_tokens
        if matched and n_cols > 0:
            # IDF-weighted: tokens in fewer columns get higher weight
            idf_sum = sum(1.0 / max(token_doc_freq.get(t, n_cols), 1) for t in matched)
            max_idf = sum(1.0 / max(token_doc_freq.get(t, n_cols), 1) for t in expanded_tokens)
            keyword_bonus = idf_sum / max_idf if max_idf > 0 else 0.0
        else:
            keyword_bonus = 0.0

        hybrid = 0.6 * float(sim) + 0.4 * keyword_bonus

        if hybrid < min_score:
            continue

        has_access = access_map.get(tbl, False)
        access = "ACCESS_GRANTED" if has_access else "NO_ACCESS \u2014 request permission"
        rows.append(dict(
            model=r["model_name"], table=tbl, column=cn,
            access_status=access,
            data_type=r["data_type"],
            rows_total=r["row_count"],
            non_null=r["non_null_count"],
            populated_pct=r["populated_pct"],
            quality=r.get("quality_flag", ""),
            relevance=round(hybrid, 3),
            description=desc or "(no description)",
        ))

    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.sort_values("relevance", ascending=False).head(top_n)
    return result
# ---------------------------------------------------------------------------


def parse_config(path: Path) -> list[TableDef]:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return [
        TableDef(
            model_name=t["model_name"],
            database_name=t.get("database_name", ALLOWED_DATABASE_NAME),
            table_name=t["table_name"],
            path=t["path"],
            fmt=t.get("format", "csv"),
            full_access_roles=tuple(t.get("full_access_roles", [])),
            profile_access_roles=tuple(t.get("profile_access_roles", [])),
            column_descriptions=t.get("column_descriptions", {}),
        )
        for t in raw.get("tables", [])
    ]


# ---------------------------------------------------------------------------
# Styling helpers
# ---------------------------------------------------------------------------


def color_quality(val: str) -> str:
    bg = FLAG_COLORS.get(val, "#ffffff")
    text = "#ffffff" if val in ("GREEN", "RED", "BLOCKED", "NO_ACCESS") else "#000000"
    return f"background-color: {bg}; color: {text}; font-weight: bold; border-radius: 4px; padding: 2px 8px"


def color_pct(val: float) -> str:
    if val >= 90.0:
        return f"background-color: {FLAG_COLORS['GREEN']}20; color: {FLAG_COLORS['GREEN']}"
    if val >= 50.0:
        return f"background-color: {FLAG_COLORS['AMBER']}20; color: {FLAG_COLORS['AMBER']}"
    return f"background-color: {FLAG_COLORS['RED']}20; color: {FLAG_COLORS['RED']}"


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Role metadata for sidebar
# ---------------------------------------------------------------------------

ROLE_INFO: dict[str, dict[str, str]] = {
    "IHKB": {
        "icon": "🏥",
        "desc": "Imperial Healthcare Knowledge Bank. View-only — no data access. Request permission to access tables.",
    },
    "researcher": {
        "icon": "🔬",
        "desc": "Profile-level access across all models. Cannot view sample values or raw data.",
    },
    "data_scientist": {
        "icon": "📊",
        "desc": "Profile-level access across all models. Cannot view sample values or raw data.",
    },
    "clinician": {
        "icon": "🩺",
        "desc": "Full access to cancer & inpatient models. Blocked from genomic/protocol tables.",
    },
    "oncologist": {
        "icon": "🧬",
        "desc": "Full access to treatment, MDT, radiotherapy & systemic therapy tables.",
    },
    "data_engineer": {
        "icon": "⚙️",
        "desc": "Full access to all tables including sample values. Can refresh materialized profiles.",
    },
    "admin": {
        "icon": "🔑",
        "desc": "Full access to all tables including sample values.",
    },
}


def _inject_css() -> None:
    """Inject custom CSS for NHS-inspired styling."""
    st.markdown("""
    <style>
    /* NHS Blue accent */
    :root {
        --nhs-blue: #005eb8;
        --nhs-dark-blue: #003087;
        --nhs-light-blue: #41b6e6;
        --nhs-green: #009639;
        --nhs-warm-yellow: #fae100;
    }

    /* Header bar */
    .main-header {
        background: linear-gradient(135deg, #003087 0%, #005eb8 100%);
        color: white;
        padding: 1.2rem 2rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        box-shadow: 0 4px 12px rgba(0, 48, 135, 0.15);
    }
    .main-header h1 {
        margin: 0; font-size: 1.8rem; font-weight: 700;
    }
    .main-header p {
        margin: 0.3rem 0 0 0; opacity: 0.85; font-size: 0.95rem;
    }

    /* Metric cards */
    .metric-card {
        background: white;
        border: 1px solid #e8e8e8;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        transition: transform 0.2s;
    }
    .metric-card:hover { transform: translateY(-2px); }
    .metric-card .metric-value {
        font-size: 2rem; font-weight: 700; color: #003087;
    }
    .metric-card .metric-label {
        font-size: 0.85rem; color: #666; margin-top: 0.2rem;
    }

    /* Quality badges */
    .badge-green { background-color: #009639; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .badge-amber { background-color: #f39c12; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
    .badge-red { background-color: #da291c; color: white; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }

    /* Sidebar role card */
    .role-card {
        background: linear-gradient(135deg, #f0f4ff 0%, #e8f0fe 100%);
        border-left: 4px solid #005eb8;
        border-radius: 8px;
        padding: 0.8rem 1rem;
        margin: 0.5rem 0;
    }
    .role-card .role-name {
        font-weight: 700; font-size: 1rem; color: #003087;
    }
    .role-card .role-desc {
        font-size: 0.82rem; color: #555; margin-top: 0.3rem;
    }

    /* Access status pills */
    .access-granted {
        background-color: #00963920; color: #009639;
        padding: 3px 12px; border-radius: 20px; font-weight: 600; font-size: 0.82rem;
        border: 1px solid #00963950;
    }
    .access-denied {
        background-color: #da291c20; color: #da291c;
        padding: 3px 12px; border-radius: 20px; font-weight: 600; font-size: 0.82rem;
        border: 1px solid #da291c50;
    }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 0.5rem 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)


def main() -> None:
    # Parse --config from CLI args passed after `--`
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("scripts/config/rbac_tables.example.json"))
    args, _ = parser.parse_known_args(sys.argv[1:])
    tables = parse_config(args.config)

    # --- Page setup ---
    st.set_page_config(page_title="Data Champs — Data Profiling Tool", layout="wide", page_icon="🔬")
    _inject_css()

    # --- Branded header ---
    st.markdown("""
    <div class="main-header">
        <h1>🔬 Data Champs — Data Profiling Tool</h1>
        <p>Imperial College Healthcare NHS Trust  ·  RBAC-governed data profiling & discovery</p>
    </div>
    """, unsafe_allow_html=True)

    # --- Sidebar ---
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        all_roles = sorted(
            {r for t in tables for r in (*t.full_access_roles, *t.profile_access_roles)}
        )
        # Add IHKB role (not in any table config)
        all_roles = ["IHKB"] + all_roles
        default_idx = next((i for i, r in enumerate(all_roles) if r == "researcher"), 0)
        role = st.selectbox("Your role", all_roles, index=default_idx)

        # Show role description card
        info = ROLE_INFO.get(role, {"icon": "👤", "desc": "Custom role."})
        st.markdown(f"""
        <div class="role-card">
            <div class="role-name">{info["icon"]}  {role.replace("_", " ").title()}</div>
            <div class="role-desc">{info["desc"]}</div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.markdown("### Governance rules")
        st.markdown(
            "- **Restricted columns:** `subject`, `encntr_id`, `episode_id`\n"
            f"- **Allowed database:** `{ALLOWED_DATABASE_NAME}`\n"
            "- **Sample values:** only for `data_engineer` / `admin`"
        )

        accessible = [t for t in tables if role in t.full_access_roles or role in t.profile_access_roles]
        st.divider()
        st.metric("Accessible tables", len(accessible))

        st.divider()
        st.markdown("### Quality flags (RAG)")
        st.markdown(
            '<span style="color:#27ae60;font-weight:bold">&#9679; GREEN</span> &ge; 90% populated<br>'
            '<span style="color:#f39c12;font-weight:bold">&#9679; AMBER</span> &ge; 50% populated<br>'
            '<span style="color:#e74c3c;font-weight:bold">&#9679; RED</span> &lt; 50% populated<br>'
            '<span style="color:#95a5a6;font-weight:bold">&#9679; BLOCKED</span> restricted by policy<br>'
            '<span style="color:#7f8c8d;font-weight:bold">&#9679; NO_ACCESS</span> role has no permission',
            unsafe_allow_html=True,
        )

    spark = get_spark()

    # --- Tabs (feasibility tab only visible to data_engineer) ---
    if role == "data_engineer":
        tab_profile, tab_search, tab_feasibility = st.tabs(
            ["📊  Data Profile", "🔍  Find Data", "📋  Feasibility Assessment"]
        )
    else:
        tab_profile, tab_search = st.tabs(["📊  Data Profile", "🔍  Find Data"])
        tab_feasibility = None

    # ---- Profile tab ----
    with tab_profile:
        if not accessible:
            # Show all tables as NO_ACCESS (e.g. for IHKB)
            db_path = Path(tables[0].path) if tables else None
            df_profile = None
            if db_path:
                df_profile = load_materialized_profile(db_path, tables, "data_engineer")
            if df_profile is not None:
                df_profile["quality"] = "NO_ACCESS"
                df_profile["suggestion"] = f"Role '{role}' has no access. Request permission."
                df_profile["samples"] = ""

                st.info(f"Role **{role}** has no direct data access. "
                        "Tables below are shown for discovery — request permission to access data.")

                n_tables = df_profile["table"].nunique()
                n_columns_shown = len(df_profile)

                m1, m2 = st.columns(2)
                m1.markdown(f'<div class="metric-card"><div class="metric-value">{n_tables}</div><div class="metric-label">Tables (view only)</div></div>', unsafe_allow_html=True)
                m2.markdown(f'<div class="metric-card"><div class="metric-value">{n_columns_shown}</div><div class="metric-label">Columns discovered</div></div>', unsafe_allow_html=True)

                display_cols = [
                    "model", "table", "column", "data_type",
                    "quality", "description", "suggestion",
                ]
                styled = (
                    df_profile[display_cols]
                    .style
                    .map(color_quality, subset=["quality"])
                )
                st.dataframe(styled, width="stretch", height=500)
            else:
                st.warning(f"Role **{role}** has no accessible tables and no profile data found.")
        else:
            # Try materialized table first (fast), fall back to live profiling
            db_path = Path(accessible[0].path)  # all tables share the same DB
            df_profile = load_materialized_profile(db_path, tables, role)

            if df_profile is not None:
                if role == "data_engineer":
                    st.caption("📦 Using pre-computed profile from `data_profile` table. "
                               "Run `make materialize` to refresh.")
            else:
                st.caption("⚙️ No materialized profile found — building and caching now…")
                with st.spinner("Profiling tables and saving to database…"):
                    df_live = build_profile(spark, tables, "data_engineer")
                    _save_profile_to_sqlite(db_path, df_live)
                df_profile = load_materialized_profile(db_path, tables, role)
                if role == "data_engineer":
                    st.caption("📦 Profile cached. Future loads will be instant.")

            # Filter out NO_ACCESS / BLOCKED rows so researchers see only their tables
            df_profile = df_profile[~df_profile["quality"].isin(["NO_ACCESS"])]

            # --- Filter controls ---
            f1, f2, f3 = st.columns(3)
            with f1:
                model_options = ["All models"] + sorted(df_profile["model"].unique().tolist())
                selected_model = st.selectbox("Model", model_options)
            with f2:
                if selected_model == "All models":
                    table_options = ["All tables"] + sorted(df_profile["table"].unique().tolist())
                else:
                    table_options = ["All tables"] + sorted(df_profile[df_profile["model"] == selected_model]["table"].unique().tolist())
                selected_table = st.selectbox("Table", table_options)
            with f3:
                quality_options = ["All qualities", "GREEN", "AMBER", "RED", "BLOCKED"]
                selected_quality = st.selectbox("Quality", quality_options)

            # Apply filters
            df_filtered = df_profile.copy()
            if selected_model != "All models":
                df_filtered = df_filtered[df_filtered["model"] == selected_model]
            if selected_table != "All tables":
                df_filtered = df_filtered[df_filtered["table"] == selected_table]
            if selected_quality != "All qualities":
                df_filtered = df_filtered[df_filtered["quality"] == selected_quality]

            # --- Summary metrics (reflect current filters) ---
            n_tables = df_filtered["table"].nunique()
            n_columns_total = len(df_profile)
            n_columns_shown = len(df_filtered)
            avg_quality = df_filtered["populated_pct"].mean() if not df_filtered.empty else 0.0
            n_green = len(df_filtered[df_filtered["quality"] == "GREEN"])
            n_amber = len(df_filtered[df_filtered["quality"] == "AMBER"])
            n_red = len(df_filtered[df_filtered["quality"] == "RED"])

            m1, m2, m3, m4 = st.columns(4)
            m1.markdown(f'<div class="metric-card"><div class="metric-value">{n_tables}</div><div class="metric-label">Tables</div></div>', unsafe_allow_html=True)
            m2.markdown(f'<div class="metric-card"><div class="metric-value">{n_columns_shown}</div><div class="metric-label">Columns shown</div></div>', unsafe_allow_html=True)
            m3.markdown(f'<div class="metric-card"><div class="metric-value">{avg_quality:.1f}%</div><div class="metric-label">Avg population</div></div>', unsafe_allow_html=True)
            m4.markdown(f'<div class="metric-card"><div class="metric-value"><span class="badge-green">{n_green}</span> <span class="badge-amber">{n_amber}</span> <span class="badge-red">{n_red}</span></div><div class="metric-label">Quality breakdown</div></div>', unsafe_allow_html=True)

            # --- Quality distribution chart (horizontal stacked bar) ---
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use("Agg")

            if not df_filtered.empty:
                # Ordered: GREEN → AMBER → RED → BLOCKED
                ordered_flags = ["GREEN", "AMBER", "RED", "BLOCKED"]
                counts = {q: len(df_filtered[df_filtered["quality"] == q]) for q in ordered_flags}
                total = sum(counts.values()) or 1

                fig, ax = plt.subplots(figsize=(8, 1.2))
                left = 0.0
                for q in ordered_flags:
                    width = counts[q] / total
                    if width > 0:
                        ax.barh(0, width, left=left, color=FLAG_COLORS.get(q, "#ccc"),
                                      edgecolor="white", linewidth=1.5, height=0.6)
                        if width > 0.12:
                            ax.text(left + width / 2, 0, f"{q}\n{counts[q]}",
                                    ha="center", va="center", fontsize=8,
                                    fontweight="bold", color="white")
                        else:
                            ax.annotate(f"{q} ({counts[q]})",
                                        xy=(left + width / 2, 0.35),
                                        ha="center", va="bottom", fontsize=7,
                                        fontweight="bold", color=FLAG_COLORS.get(q, "#333"))
                        left += width

                ax.set_xlim(0, 1)
                ax.set_ylim(-0.5, 0.8)
                ax.axis("off")
                fig.patch.set_alpha(0)
                fig.subplots_adjust(left=0, right=1, top=0.85, bottom=0.05)
                st.pyplot(fig, width="stretch")
                plt.close(fig)

            st.caption(f"Showing {n_columns_shown} of {n_columns_total} columns")

            # Apply display logic: hide sample column for non-privileged roles
            display_cols = [
                "model", "table", "column", "data_type",
                "rows_total", "non_null", "populated_pct",
                "distinct", "quality", "description", "suggestion",
            ]
            if role in ROLES_WITH_SAMPLE_ACCESS:
                display_cols.insert(-2, "samples")

            styled = (
                df_filtered[display_cols]
                .style
                .map(color_quality, subset=["quality"])
                .map(color_pct, subset=["populated_pct"])
            )
            st.dataframe(styled, width="stretch", height=500)

            # Download button
            csv_data = df_filtered[display_cols].to_csv(index=False)
            st.download_button(
                "⬇️  Download profile CSV",
                csv_data,
                file_name="data_profile.csv",
                mime="text/csv",
            )

    # ---- Search tab ----
    with tab_search:
        st.markdown(
            "Describe what data you need in **plain English**. "
            "We search across **all** tables — including ones you may need to request access to."
        )

        # Pick up query from example button click (if any)
        default_query = st.session_state.pop("search_query", "")

        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            query = st.text_input(
                "What data are you looking for?",
                value=default_query,
                placeholder="e.g. mortality, smoking history, blood test results",
                label_visibility="collapsed",
            )
        with search_col2:
            search_mode = st.radio(
                "Mode",
                ["🧠 Smart", "🔤 Keyword"],
                index=0,
                horizontal=True,
                label_visibility="collapsed",
            )
        use_semantic = search_mode.startswith("🧠")

        if query:
            with st.spinner("Searching …"):
                db_path = Path(tables[0].path)  # all tables share the same DB
                if use_semantic:
                    df_search = search_columns_semantic(db_path, tables, role, query)
                else:
                    df_search = search_columns(db_path, tables, role, query)

            if df_search.empty:
                st.warning("No matching columns found. Try different keywords.")
            else:
                n_accessible = len(df_search[df_search["access_status"] == "ACCESS_GRANTED"])
                n_restricted = len(df_search[df_search["access_status"] != "ACCESS_GRANTED"])

                # Summary pills
                st.markdown(f"""
                <div style="display: flex; gap: 12px; margin-bottom: 1rem;">
                    <div style="background: #005eb810; border: 1px solid #005eb830; border-radius: 20px; padding: 6px 16px; font-size: 0.9rem;">
                        🔎  <strong>{len(df_search)}</strong> matches
                    </div>
                    <div class="access-granted">✅  {n_accessible} accessible</div>
                    {f'<div class="access-denied">🔒  {n_restricted} require permission</div>' if n_restricted else ''}
                </div>
                """, unsafe_allow_html=True)

                # Show results as expandable cards + table
                for _, row in df_search.iterrows():
                    is_granted = row["access_status"] == "ACCESS_GRANTED"
                    access_badge = (
                        '<span class="access-granted">✅ Accessible</span>'
                        if is_granted else
                        '<span class="access-denied">🔒 Request access</span>'
                    )
                    quality_cls = row["quality"].lower() if row["quality"] in ("GREEN", "AMBER", "RED") else "red"
                    quality_badge = f'<span class="badge-{quality_cls}">{row["quality"]}</span>'

                    with st.expander(
                        f"**{row['table']}** . {row['column']}  —  relevance: {row['relevance']}",
                        expanded=False,
                    ):
                        st.markdown(f"""
                        <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 0.5rem;">
                            {access_badge}  {quality_badge}
                            <span style="color: #888; font-size: 0.85rem;">Model: {row['model']}  ·  Type: {row['data_type']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown(f"📝 **Description:** {row['description']}")
                        col_a, col_b, col_c = st.columns(3)
                        col_a.metric("Rows", f"{row['rows_total']:,}")
                        col_b.metric("Non-null", f"{row['non_null']:,}")
                        col_c.metric("Populated", f"{row['populated_pct']:.1f}%")

                st.markdown("---")

                # Also show as table for copy-paste
                with st.expander("📋 View as table", expanded=False):
                    def color_access(val: str) -> str:
                        if val == "ACCESS_GRANTED":
                            return "background-color: #27ae6030; color: #27ae60; font-weight: bold"
                        return "background-color: #e74c3c30; color: #e74c3c; font-weight: bold"

                    styled_search = (
                        df_search.style
                        .map(color_access, subset=["access_status"])
                        .map(color_quality, subset=["quality"])
                        .background_gradient(subset=["relevance"], cmap="YlGn")
                    )
                    st.dataframe(styled_search, width="stretch", height=400)

                csv_search = df_search.to_csv(index=False)
                st.download_button(
                    "⬇️  Download search results CSV",
                    csv_search,
                    file_name="search_results.csv",
                    mime="text/csv",
                )
        else:
            # Show example queries as clickable buttons that populate the search
            st.markdown("**💡 Try searching for:**")
            examples = [
                "mortality",
                "smoking history",
                "blood test results",
                "treatment response",
                "date of birth",
                "genomic variants",
            ]
            ex_cols = st.columns(len(examples))
            for i, ex in enumerate(examples):
                with ex_cols[i]:
                    if st.button(ex, key=f"example_{i}", use_container_width=True):
                        st.session_state["search_query"] = ex
                        st.rerun()

    # ---- Feasibility tab (data_engineer only) ----
    if tab_feasibility is not None:
        with tab_feasibility:
            import matplotlib.pyplot as plt
            import matplotlib
            matplotlib.use("Agg")

            feas_path = Path("data/processed/feasibility_assessment.csv")
            if not feas_path.exists():
                st.warning(
                    "No feasibility assessment found at `data/processed/feasibility_assessment.csv`.\n\n"
                    "Run the feasibility script first."
                )
            else:
                df_feas = pd.read_csv(feas_path)

                # --- KPI row ---
                total_pts = len(df_feas)
                n_green = len(df_feas[df_feas["rag_score"] == "GREEN"])
                n_amber = len(df_feas[df_feas["rag_score"] == "AMBER"])
                n_red = len(df_feas[df_feas["rag_score"] == "RED"])
                avg_score = df_feas["feasibility_score"].mean()
                coverage_pct = (n_green + n_amber) / total_pts * 100 if total_pts else 0

                k1, k2, k3, k4 = st.columns(4)
                k1.markdown(f'<div class="metric-card"><div class="metric-value">{total_pts}</div><div class="metric-label">Data points requested</div></div>', unsafe_allow_html=True)
                k2.markdown(f'<div class="metric-card"><div class="metric-value">{avg_score:.2f}</div><div class="metric-label">Avg feasibility score</div></div>', unsafe_allow_html=True)
                k3.markdown(f'<div class="metric-card"><div class="metric-value">{coverage_pct:.0f}%</div><div class="metric-label">Coverage (GREEN + AMBER)</div></div>', unsafe_allow_html=True)
                k4.markdown(f'<div class="metric-card"><div class="metric-value"><span class="badge-green">{n_green}</span> <span class="badge-amber">{n_amber}</span> <span class="badge-red">{n_red}</span></div><div class="metric-label">RAG breakdown</div></div>', unsafe_allow_html=True)

                # --- RAG stacked bar ---
                ordered = ["GREEN", "AMBER", "RED"]
                counts = {q: len(df_feas[df_feas["rag_score"] == q]) for q in ordered}
                bar_total = sum(counts.values()) or 1
                fig, ax = plt.subplots(figsize=(8, 1.2))
                left = 0.0
                for q in ordered:
                    w = counts[q] / bar_total
                    if w > 0:
                        ax.barh(0, w, left=left, color=FLAG_COLORS.get(q, "#ccc"),
                                edgecolor="white", linewidth=1.5, height=0.6)
                        if w > 0.12:
                            ax.text(left + w / 2, 0, f"{q}\n{counts[q]}",
                                    ha="center", va="center", fontsize=8,
                                    fontweight="bold", color="white")
                        else:
                            ax.annotate(f"{q} ({counts[q]})",
                                        xy=(left + w / 2, 0.35),
                                        ha="center", va="bottom", fontsize=7,
                                        fontweight="bold", color=FLAG_COLORS.get(q, "#333"))
                        left += w
                ax.set_xlim(0, 1)
                ax.set_ylim(-0.5, 0.8)
                ax.axis("off")
                fig.patch.set_alpha(0)
                fig.subplots_adjust(left=0, right=1, top=0.85, bottom=0.05)
                st.pyplot(fig, width="stretch")
                plt.close(fig)

                # --- Domain filter ---
                domains = ["All domains"] + sorted(df_feas["domain"].unique().tolist())
                selected_domain = st.selectbox("Filter by domain", domains, key="feas_domain")

                df_feas_filtered = df_feas.copy()
                if selected_domain != "All domains":
                    df_feas_filtered = df_feas_filtered[df_feas_filtered["domain"] == selected_domain]

                # --- Feasibility by domain chart ---
                domain_summary = (
                    df_feas_filtered.groupby("domain")
                    .agg(
                        total=("request_id", "count"),
                        avg_score=("feasibility_score", "mean"),
                        green=("rag_score", lambda x: (x == "GREEN").sum()),
                        amber=("rag_score", lambda x: (x == "AMBER").sum()),
                        red=("rag_score", lambda x: (x == "RED").sum()),
                    )
                    .sort_values("avg_score", ascending=True)
                    .reset_index()
                )

                if len(domain_summary) > 1:
                    fig2, ax2 = plt.subplots(figsize=(8, max(2.5, len(domain_summary) * 0.45)))
                    y_pos = range(len(domain_summary))
                    ax2.barh(y_pos, domain_summary["green"], color=FLAG_COLORS["GREEN"],
                             label="GREEN", edgecolor="white", linewidth=0.5)
                    ax2.barh(y_pos, domain_summary["amber"], left=domain_summary["green"],
                             color=FLAG_COLORS["AMBER"], label="AMBER", edgecolor="white", linewidth=0.5)
                    ax2.barh(y_pos, domain_summary["red"],
                             left=domain_summary["green"] + domain_summary["amber"],
                             color=FLAG_COLORS["RED"], label="RED", edgecolor="white", linewidth=0.5)
                    ax2.set_yticks(y_pos)
                    ax2.set_yticklabels(domain_summary["domain"], fontsize=9)
                    ax2.set_xlabel("Data points", fontsize=9)
                    ax2.set_title("Feasibility by Domain", fontsize=11, fontweight="bold", pad=10)
                    ax2.legend(loc="lower right", fontsize=8)
                    ax2.spines["top"].set_visible(False)
                    ax2.spines["right"].set_visible(False)
                    fig2.patch.set_alpha(0)
                    fig2.tight_layout()
                    st.pyplot(fig2, width="stretch")
                    plt.close(fig2)

                # --- Detail table with expandable cards ---
                st.markdown(f"**Showing {len(df_feas_filtered)} data points**")

                for _, row in df_feas_filtered.iterrows():
                    rag = row["rag_score"]
                    rag_cls = rag.lower() if rag in ("GREEN", "AMBER", "RED") else "red"
                    rag_badge = f'<span class="badge-{rag_cls}">{rag}</span>'
                    score_str = f"{row['feasibility_score']:.3f}" if row["feasibility_score"] > 0 else "0.000"

                    with st.expander(
                        f"{row['request_id']}  —  {row['data_point_name']}  ({row['domain']})  —  {rag}",
                        expanded=False,
                    ):
                        st.markdown(f"""
                        <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 0.5rem;">
                            {rag_badge}
                            <span style="color: #888; font-size: 0.85rem;">Domain: {row['domain']}</span>
                        </div>
                        """, unsafe_allow_html=True)

                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Feasibility", score_str)
                        c2.metric("Populated", f"{row['populated_pct']:.1f}%")
                        c3.metric("Rows", f"{int(row['row_count']):,}" if row["row_count"] > 0 else "—")
                        c4.metric("Distinct", f"{int(row['distinct_count']):,}" if row["distinct_count"] > 0 else "—")

                        if row["table_name"] != "-":
                            st.markdown(f"📍 **Matched:** `{row['table_name']}.{row['column_name']}` ({row['data_type']})")
                        st.markdown(f"💬 **Recommendation:** {row['recommendation']}")

                # --- Download ---
                csv_feas = df_feas_filtered.to_csv(index=False)
                st.download_button(
                    "⬇️  Download feasibility CSV",
                    csv_feas,
                    file_name="feasibility_assessment.csv",
                    mime="text/csv",
                )


if __name__ == "__main__":
    main()
