#!/usr/bin/env python3
"""Build a clinical trial eligibility report enriched with table datapoints.

For consented patients (patient_consent = 'Y'), the report includes:
- Patient-level clinical trial datapoints from the consent table
- Record counts across eligibility-related table families
- Eligibility score and tier
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


ELIGIBILITY_CRITERIA = {
    "cancer_diagnoses": "Cancer Diagnoses",
    "cancer_staging": "Cancer Staging",
    "cancer_treatments": "Cancer Treatments",
    "pathology_specimens": "Pathology Specimens",
    "secondary_care_admissions": "Secondary Care Admissions",
    "secondary_care_procedures": "Secondary Care Procedures",
}


def get_tables(conn: sqlite3.Connection) -> list[str]:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cur.fetchall()]


def table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in cur.fetchall())


def get_consented_patient_set(conn: sqlite3.Connection) -> set[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT patient_sk
        FROM cerner_raw__cancer_clinical_trials
        WHERE patient_consent = 'Y'
        """
    )
    return {row[0] for row in cur.fetchall()}


def get_latest_trial_datapoints(conn: sqlite3.Connection, consented_patients: set[str]) -> dict[str, dict[str, str]]:
    """Return latest trial datapoints per consented patient from consent table."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            patient_sk,
            trial_id,
            trial_name,
            trial_phase,
            enrollment_date,
            cancer_type,
            disease_status,
            treatment_arm,
            patient_consent,
            consent_date,
            withdrawal_date,
            trial_status
        FROM cerner_raw__cancer_clinical_trials
        WHERE patient_consent = 'Y'
        ORDER BY patient_sk, consent_date DESC, enrollment_date DESC, row_id DESC
        """
    )

    per_patient: dict[str, dict[str, str]] = {}
    trial_record_counts: Counter = Counter()

    for row in cur.fetchall():
        patient_sk = row[0]
        trial_record_counts[patient_sk] += 1

        # Keep first row only because result is already ordered by most recent.
        if patient_sk in per_patient:
            continue

        per_patient[patient_sk] = {
            "latest_trial_id": row[1] or "",
            "latest_trial_name": row[2] or "",
            "latest_trial_phase": row[3] or "",
            "latest_enrollment_date": row[4] or "",
            "latest_cancer_type": row[5] or "",
            "latest_disease_status": row[6] or "",
            "latest_treatment_arm": row[7] or "",
            "patient_consent": row[8] or "",
            "latest_consent_date": row[9] or "",
            "latest_withdrawal_date": row[10] or "",
            "latest_trial_status": row[11] or "",
        }

    for patient in consented_patients:
        per_patient.setdefault(
            patient,
            {
                "latest_trial_id": "",
                "latest_trial_name": "",
                "latest_trial_phase": "",
                "latest_enrollment_date": "",
                "latest_cancer_type": "",
                "latest_disease_status": "",
                "latest_treatment_arm": "",
                "patient_consent": "Y",
                "latest_consent_date": "",
                "latest_withdrawal_date": "",
                "latest_trial_status": "",
            },
        )
        per_patient[patient]["consented_trial_records"] = str(trial_record_counts.get(patient, 0))

    return per_patient


def get_criterion_counts(
    conn: sqlite3.Connection,
    consented_patients: set[str],
    all_tables: list[str],
) -> tuple[dict[str, dict[str, int]], dict[str, set[str]]]:
    """Aggregate per-patient record counts for each eligibility criterion."""
    criterion_patient_counts: dict[str, dict[str, int]] = {
        key: defaultdict(int) for key in ELIGIBILITY_CRITERIA
    }
    criterion_patients_present: dict[str, set[str]] = {key: set() for key in ELIGIBILITY_CRITERIA}

    for criterion_key in ELIGIBILITY_CRITERIA:
        matching_tables = [t for t in all_tables if criterion_key in t and table_has_column(conn, t, "patient_sk")]

        for table_name in matching_tables:
            cur = conn.cursor()
            cur.execute(f"SELECT patient_sk, COUNT(*) FROM {table_name} GROUP BY patient_sk")
            for patient_sk, count in cur.fetchall():
                if patient_sk not in consented_patients:
                    continue
                criterion_patient_counts[criterion_key][patient_sk] += int(count)
                criterion_patients_present[criterion_key].add(patient_sk)

    return criterion_patient_counts, criterion_patients_present


def calculate_status(score_pct: float) -> str:
    if score_pct >= 80:
        return "ELIGIBLE - High"
    if score_pct >= 60:
        return "ELIGIBLE - Moderate"
    if score_pct >= 40:
        return "ELIGIBLE - Low"
    return "INELIGIBLE - Insufficient Data"


def generate_report(db_path: str, output_path: str) -> None:
    conn = sqlite3.connect(db_path)

    consented_patients = get_consented_patient_set(conn)
    all_tables = get_tables(conn)
    latest_trial_datapoints = get_latest_trial_datapoints(conn, consented_patients)
    criterion_counts, criterion_patients_present = get_criterion_counts(conn, consented_patients, all_tables)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "patient_sk",
        "patient_consent",
        "consented_trial_records",
        "latest_trial_id",
        "latest_trial_name",
        "latest_trial_phase",
        "latest_enrollment_date",
        "latest_cancer_type",
        "latest_disease_status",
        "latest_treatment_arm",
        "latest_trial_status",
        "latest_consent_date",
        "latest_withdrawal_date",
        "cancer_diagnoses_records",
        "cancer_staging_records",
        "cancer_treatments_records",
        "pathology_specimens_records",
        "secondary_care_admissions_records",
        "secondary_care_procedures_records",
        "criteria_met",
        "total_criteria",
        "eligibility_score_pct",
        "eligibility_status",
    ]

    total_criteria = len(ELIGIBILITY_CRITERIA)
    status_counter: Counter = Counter()

    with output_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()

        for patient_sk in sorted(consented_patients):
            row = {
                "patient_sk": patient_sk,
                **latest_trial_datapoints[patient_sk],
                "cancer_diagnoses_records": criterion_counts["cancer_diagnoses"].get(patient_sk, 0),
                "cancer_staging_records": criterion_counts["cancer_staging"].get(patient_sk, 0),
                "cancer_treatments_records": criterion_counts["cancer_treatments"].get(patient_sk, 0),
                "pathology_specimens_records": criterion_counts["pathology_specimens"].get(patient_sk, 0),
                "secondary_care_admissions_records": criterion_counts["secondary_care_admissions"].get(patient_sk, 0),
                "secondary_care_procedures_records": criterion_counts["secondary_care_procedures"].get(patient_sk, 0),
            }

            criteria_met = sum(
                1
                for key in ELIGIBILITY_CRITERIA
                if criterion_counts[key].get(patient_sk, 0) > 0
            )
            score_pct = (criteria_met / total_criteria) * 100
            status = calculate_status(score_pct)

            row["criteria_met"] = criteria_met
            row["total_criteria"] = total_criteria
            row["eligibility_score_pct"] = f"{score_pct:.1f}%"
            row["eligibility_status"] = status
            status_counter[status] += 1

            writer.writerow(row)

    print(f"Analyzed consented patients: {len(consented_patients)}")
    print(f"Wrote enriched report: {output_file}")
    print("Eligibility distribution:")
    for status, count in sorted(status_counter.items()):
        pct = (count / len(consented_patients) * 100) if consented_patients else 0
        print(f"  {status}: {count} ({pct:.1f}%)")

    print("Criteria availability among consented patients:")
    for key, label in ELIGIBILITY_CRITERIA.items():
        count = len(criterion_patients_present[key])
        pct = (count / len(consented_patients) * 100) if consented_patients else 0
        print(f"  {label}: {count}/{len(consented_patients)} ({pct:.1f}%)")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate enriched trial eligibility report for consented patients"
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default="data/dwh/mock_feasibility_sqlite.db",
        help="Path to SQLite database",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default="data/processed/trial_eligibility_report.csv",
        help="Path to output CSV",
    )
    args = parser.parse_args()
    generate_report(args.db_path, args.output_path)
