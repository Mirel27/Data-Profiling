#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


# This mapping is taken manually from docs/raw_demo_database_readme.md.
DOCUMENTED_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "raw_cancer_patients": ("YOB", "reg_dt", "dod"),
    "raw_cancer_diagnoses": (
        "dx_date",
        "TumourSite",
        "ICD10_code",
        "Clinical_Stage",
        "morph_icdo3",
    ),
    "raw_inpatient_spells": ("adm_date", "dis_date", "LOS_days", "Adm_Method"),
    "raw_inpatient_episodes": (
        "ep_start_dt",
        "ep_end_dt",
        "cons_code",
        "proc_OPCS4",
        "Dx_ICD10",
        "cost_GBP",
    ),
    "raw_cancer_treatments": ("Tx_start_date", "Tx_modality", "Tx_response"),
    "raw_lab_results": ("request_dt", "result_numeric", "sys_source"),
    "raw_cancer_outcomes": ("OS_days", "PFS_days", "EA_90d_flag"),
    "raw_pathology_reports": ("spec_date", "histo_result", "src_system"),
    "raw_imaging_reports": ("img_date", "RECIST_resp", "pacs_src"),
    "raw_genomic_variants": ("ngs_date", "ClinVar_class", "TMB", "MSI", "seq_lab"),
    "raw_radiotherapy_fractions": (
        "fx_date",
        "presc_dose_Gy",
        "deliv_dose_Gy",
        "attend_status",
    ),
    "raw_systemic_therapy_orders": (
        "ord_date",
        "plan_dose_mg",
        "admin_flag",
        "px_system",
    ),
    "raw_mdt_decisions": (
        "mdt_date",
        "rec_plan",
        "trial_eligib_flag",
        "Tx_intent",
        "mdt_src",
    ),
    "raw_vte_risk_assessments": (
        "padua_score",
        "caprini_score",
        "vte_high_risk_flag",
        "pharm_px_rx",
    ),
    "raw_vte_events": ("vte_type", "anatom_site", "ha_vte_flag", "icd10_vte"),
    "raw_vte_prophylaxis_admin": (
        "px_type",
        "px_drug",
        "dose_mg",
        "missed_dose_flag",
        "contraind_flag",
    ),
    "raw_falls_risk_screenings": (
        "morse_score",
        "mobility_lvl",
        "prior_fall_6m_flag",
        "falls_high_risk_flag",
    ),
    "raw_falls_incidents": (
        "fall_loc",
        "unwitnessed_flag",
        "head_strike_flag",
        "injury_severity",
    ),
    "raw_falls_post_event_reviews": (
        "repeat_fall_7d_flag",
        "action_plan",
        "reviewer_role",
    ),
}

DOCUMENTED_PATTERN_COLUMNS: dict[str, tuple[str, ...]] = {
    "raw_inpatient_observations_": (
        "obs_dt",
        "HR",
        "SBP",
        "RR",
        "temp_C",
        "NEWS2",
        "ward_loc",
    ),
    "raw_cancer_registry_": (
        "extract_dt",
        "cwt_62d_flag",
        "mdt_disc_flag",
        "trial_elig_flag",
        "travel_dist_km",
        "IMD_decile",
        "dq_status",
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check that the schema documented in docs/raw_demo_database_readme.md exists in raw_demo.db."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/dwh/raw_demo.db"),
        help="Path to the SQLite database to validate.",
    )
    return parser


def table_columns(cur: sqlite3.Cursor, table_name: str) -> set[str]:
    return {
        row[1]
        for row in cur.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def main() -> int:
    args = build_parser().parse_args()
    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    failures: list[str] = []

    try:
        print(f"Checking documented schema against: {args.db}")
        print()
        print("Concrete tables")
        for table_name, expected_columns in DOCUMENTED_TABLE_COLUMNS.items():
            columns = table_columns(cur, table_name)
            if not columns:
                failures.append(f"Missing table: {table_name}")
                print(f"FAIL  {table_name}: table missing")
                continue

            missing_columns = [
                column_name
                for column_name in expected_columns
                if column_name not in columns
            ]
            if missing_columns:
                failures.append(
                    f"Missing columns in {table_name}: {', '.join(missing_columns)}"
                )
                print(
                    f"FAIL  {table_name}: missing columns -> {', '.join(missing_columns)}"
                )
            else:
                print(
                    f"PASS  {table_name}: all {len(expected_columns)} documented columns found"
                )

        print()
        print("Pattern tables")
        for prefix, expected_columns in DOCUMENTED_PATTERN_COLUMNS.items():
            matching_tables = [
                row[0]
                for row in cur.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type='table' AND name LIKE ?
                    ORDER BY name
                    """,
                    (f"{prefix}%",),
                ).fetchall()
            ]

            if not matching_tables:
                failures.append(f"No tables found for pattern: {prefix}XXXX")
                print(f"FAIL  {prefix}XXXX: no matching tables found")
                continue

            bad_tables: list[str] = []
            for table_name in matching_tables:
                columns = table_columns(cur, table_name)
                missing_columns = [
                    column_name
                    for column_name in expected_columns
                    if column_name not in columns
                ]
                if missing_columns:
                    bad_tables.append(
                        f"{table_name} -> missing {', '.join(missing_columns)}"
                    )

            if bad_tables:
                failures.extend(bad_tables)
                print(f"FAIL  {prefix}XXXX: schema mismatch in {len(bad_tables)} table(s)")
                for bad_table in bad_tables:
                    print(f"      {bad_table}")
            else:
                print(
                    f"PASS  {prefix}XXXX: {len(matching_tables)} matching table(s) all contain documented columns"
                )

        print()
        if failures:
            print(f"Schema check failed with {len(failures)} issue(s).")
            return 1

        print("Schema check passed.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
