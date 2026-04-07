from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.generate_raw_demo_db import SimulationConfig, simulate_local_raw_db


class GenerateRawDemoDbTests(unittest.TestCase):
    def test_generates_expected_enriched_raw_source_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "raw_demo.db"
            config = SimulationConfig(db_path=db_path)

            result = simulate_local_raw_db(config)

            self.assertEqual(str(db_path), result["database"])
            self.assertEqual(50, result["tables_created"])
            self.assertTrue(db_path.exists())

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            raw_table_count = cur.execute(
                """
                SELECT COUNT(*)
                FROM sqlite_master
                WHERE type='table' AND name LIKE 'raw_%'
                """
            ).fetchone()[0]
            self.assertEqual(50, raw_table_count)

            self.assertEqual(
                200,
                cur.execute("SELECT COUNT(*) FROM raw_cancer_patients").fetchone()[0],
            )
            self.assertEqual(
                240,
                cur.execute("SELECT COUNT(*) FROM raw_cancer_diagnoses").fetchone()[0],
            )
            self.assertEqual(
                360,
                cur.execute("SELECT COUNT(*) FROM raw_inpatient_spells").fetchone()[0],
            )
            self.assertEqual(
                700,
                cur.execute("SELECT COUNT(*) FROM raw_lab_results").fetchone()[0],
            )
            self.assertEqual(
                396,
                cur.execute("SELECT COUNT(*) FROM raw_vte_risk_assessments").fetchone()[0],
            )
            self.assertEqual(
                70,
                cur.execute("SELECT COUNT(*) FROM raw_vte_events").fetchone()[0],
            )
            self.assertEqual(
                503,
                cur.execute("SELECT COUNT(*) FROM raw_vte_prophylaxis_admin").fetchone()[0],
            )
            self.assertEqual(
                468,
                cur.execute("SELECT COUNT(*) FROM raw_falls_risk_screenings").fetchone()[0],
            )
            self.assertEqual(
                56,
                cur.execute("SELECT COUNT(*) FROM raw_falls_incidents").fetchone()[0],
            )
            self.assertEqual(
                52,
                cur.execute("SELECT COUNT(*) FROM raw_falls_post_event_reviews").fetchone()[0],
            )

            first_patient = cur.execute(
                """
                SELECT *
                FROM raw_cancer_patients
                ORDER BY patient_sk
                LIMIT 1
                """
            ).fetchone()
            self.assertEqual(
                (
                    "PT000001",
                    "ANON46913810",
                    "F",
                    1963,
                    "asian",
                    "LSOA23434",
                    "never",
                    25.9,
                    1,
                    "2025-12-05",
                    None,
                    0,
                    "2026-03-17T16:12:34",
                ),
                first_patient,
            )

            conn.close()


if __name__ == "__main__":
    unittest.main()
