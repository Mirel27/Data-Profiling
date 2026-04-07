from __future__ import annotations

import sqlite3
import unittest
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
    "raw_radiotherapy_fractions": ("fx_date", "presc_dose_Gy", "deliv_dose_Gy", "attend_status"),
    "raw_systemic_therapy_orders": ("ord_date", "plan_dose_mg", "admin_flag", "px_system"),
    "raw_mdt_decisions": ("mdt_date", "rec_plan", "trial_eligib_flag", "Tx_intent", "mdt_src"),
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
    "raw_inpatient_observations_": ("obs_dt", "HR", "SBP", "RR", "temp_C", "NEWS2", "ward_loc"),
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


class RawDemoReadmeSchemaTests(unittest.TestCase):
    DB_PATH = Path("data/dwh/raw_demo.db")

    def setUp(self) -> None:
        self.assertTrue(
            self.DB_PATH.exists(),
            f"Expected source database at {self.DB_PATH}",
        )
        self.conn = sqlite3.connect(self.DB_PATH)
        self.cur = self.conn.cursor()

    def tearDown(self) -> None:
        self.conn.close()

    def table_columns(self, table_name: str) -> set[str]:
        return {
            row[1]
            for row in self.cur.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    def test_documented_tables_and_columns_exist(self) -> None:
        for table_name, expected_columns in DOCUMENTED_TABLE_COLUMNS.items():
            with self.subTest(table=table_name):
                columns = self.table_columns(table_name)
                self.assertGreater(
                    len(columns),
                    0,
                    f"Documented table '{table_name}' does not exist in {self.DB_PATH}",
                )
                for column_name in expected_columns:
                    self.assertIn(
                        column_name,
                        columns,
                        f"Documented column '{column_name}' missing from table '{table_name}'",
                    )

    def test_documented_pattern_tables_exist_and_match_columns(self) -> None:
        for prefix, expected_columns in DOCUMENTED_PATTERN_COLUMNS.items():
            with self.subTest(prefix=prefix):
                matching_tables = [
                    row[0]
                    for row in self.cur.execute(
                        """
                        SELECT name
                        FROM sqlite_master
                        WHERE type='table' AND name LIKE ?
                        ORDER BY name
                        """,
                        (f"{prefix}%",),
                    ).fetchall()
                ]
                self.assertGreater(
                    len(matching_tables),
                    0,
                    f"No tables found matching documented pattern '{prefix}XXXX'",
                )
                for table_name in matching_tables:
                    columns = self.table_columns(table_name)
                    for column_name in expected_columns:
                        self.assertIn(
                            column_name,
                            columns,
                            f"Documented column '{column_name}' missing from table '{table_name}'",
                        )


if __name__ == "__main__":
    unittest.main()
