#!/usr/bin/env python3
"""Analyze datapoints for consented patients in the clinical trial table.

This script identifies patient characteristics and trial information for patients
who have provided consent (patient_consent = 'Y') in the clinical trials table.

Run:
    python scripts/analyze_consented_patients.py [db_path] [output_path]

Example:
    python scripts/analyze_consented_patients.py data/dwh/mock_feasibility_sqlite.db data/processed/consented_patients_analysis.csv
"""

import argparse
import sqlite3
import csv
from pathlib import Path
from collections import defaultdict, Counter
from typing import Any


def analyze_consented_patients(db_path: str, output_path: str) -> None:
    """Analyze datapoints for consented patients.
    
    Args:
        db_path: Path to the SQLite database
        output_path: Path to output CSV file with results
    """
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Analyzing consented patients from {db_path}...")
    
    # Query consented patients with all their datapoints
    query = """
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
        trial_status,
        source_system,
        record_date
    FROM cerner_raw__cancer_clinical_trials
    WHERE patient_consent = 'Y'
    ORDER BY patient_sk, enrollment_date
    """
    
    cursor.execute(query)
    
    # Extract results
    consented_patients = cursor.fetchall()
    columns = [description[0] for description in cursor.description]
    
    conn.close()
    
    print(f"✓ Found {len(consented_patients)} consented patient records")
    
    # Analyze datapoints
    if len(consented_patients) > 0:
        # Write detailed records to CSV
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(consented_patients)
        
        print(f"✓ Written {len(consented_patients)} consented patient records to {output_path}")
        
        # Compute statistics
        print("\n=== ANALYSIS: CONSENTED PATIENTS DATAPOINTS ===\n")
        
        # Convert to dict for easier analysis
        patient_records = [dict(zip(columns, row)) for row in consented_patients]
        
        # 1. Unique patients
        unique_patients = set(row['patient_sk'] for row in patient_records)
        print(f"Unique Consented Patients: {len(unique_patients)}")
        
        # 2. Cancer type distribution
        cancer_types = Counter(row['cancer_type'] for row in patient_records)
        print(f"\nCancer Type Distribution (Top 5):")
        for cancer_type, count in cancer_types.most_common(5):
            pct = (count / len(patient_records) * 100)
            print(f"  - {cancer_type}: {count} ({pct:.1f}%)")
        
        # 3. Disease status distribution
        disease_statuses = Counter(row['disease_status'] for row in patient_records)
        print(f"\nDisease Status Distribution:")
        for status, count in sorted(disease_statuses.items(), key=lambda x: -x[1]):
            pct = (count / len(patient_records) * 100)
            print(f"  - {status}: {count} ({pct:.1f}%)")
        
        # 4. Treatment arm distribution
        treatment_arms = Counter(row['treatment_arm'] for row in patient_records)
        print(f"\nTreatment Arm Distribution:")
        for arm, count in sorted(treatment_arms.items(), key=lambda x: -x[1]):
            pct = (count / len(patient_records) * 100)
            print(f"  - {arm}: {count} ({pct:.1f}%)")
        
        # 5. Trial phase distribution
        trial_phases = Counter(row['trial_phase'] for row in patient_records)
        print(f"\nTrial Phase Distribution:")
        for phase, count in sorted(trial_phases.items(), key=lambda x: -x[1]):
            pct = (count / len(patient_records) * 100)
            print(f"  - {phase}: {count} ({pct:.1f}%)")
        
        # 6. Trial status distribution
        trial_statuses = Counter(row['trial_status'] for row in patient_records)
        print(f"\nTrial Status Distribution:")
        for status, count in sorted(trial_statuses.items(), key=lambda x: -x[1]):
            pct = (count / len(patient_records) * 100)
            print(f"  - {status}: {count} ({pct:.1f}%)")
        
        # 7. Withdrawal rate
        withdrawn = sum(1 for row in patient_records if row['withdrawal_date'] is not None)
        withdrawal_pct = (withdrawn / len(patient_records) * 100) if len(patient_records) > 0 else 0
        print(f"\nWithdrawal Rate: {withdrawn} ({withdrawal_pct:.1f}%)")
        
        # 8. Datapoint completeness
        print(f"\nDatapoint Completeness (for {len(patient_records)} records):")
        for col in columns:
            non_null = sum(1 for row in patient_records if row[col] is not None and row[col] != '')
            completeness = (non_null / len(patient_records) * 100) if len(patient_records) > 0 else 0
            print(f"  - {col}: {non_null}/{len(patient_records)} ({completeness:.1f}%)")
        
        # 9. Enrollment date range
        enrollment_dates = sorted([row['enrollment_date'] for row in patient_records if row['enrollment_date']])
        if enrollment_dates:
            print(f"\nEnrollment Date Range:")
            print(f"  - Earliest: {enrollment_dates[0]}")
            print(f"  - Latest: {enrollment_dates[-1]}")
        
        # 10. Unique trials
        unique_trials = set(row['trial_id'] for row in patient_records)
        print(f"\nUnique Trials: {len(unique_trials)}")
        
        print(f"\n✓ Analysis complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze datapoints for consented patients"
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default="data/dwh/mock_feasibility_sqlite.db",
        help="Path to the SQLite database file"
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        default="data/processed/consented_patients_analysis.csv",
        help="Path to output CSV file"
    )
    
    args = parser.parse_args()
    analyze_consented_patients(args.db_path, args.output_path)
