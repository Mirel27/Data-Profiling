#!/usr/bin/env python3
"""Create a mock cancer clinical trial table in the mock_feasibility_sqlite.db database.

This script adds a clinical trial table with 10,000 rows including patient consent flags.

Run:
    python scripts/create_clinical_trial_table.py [db_path] [num_rows]

Example:
    python scripts/create_clinical_trial_table.py data/dwh/mock_feasibility_sqlite.db 10000
"""

import argparse
import sqlite3
import random
from datetime import datetime, timedelta
from pathlib import Path


def create_clinical_trial_table(db_path: str, num_rows: int = 10000) -> None:
    """Create a clinical trial table with mock data.
    
    Args:
        db_path: Path to the SQLite database file
        num_rows: Number of rows to generate (default: 10000)
    """
    # Ensure database directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"Creating clinical trial table in {db_path}...")
    
    # Drop existing table if it exists
    cursor.execute("DROP TABLE IF EXISTS cerner_raw__cancer_clinical_trials")
    
    # Create table
    cursor.execute("""
        CREATE TABLE cerner_raw__cancer_clinical_trials (
            row_id INTEGER PRIMARY KEY,
            patient_sk TEXT NOT NULL,
            trial_id TEXT NOT NULL,
            trial_name TEXT,
            trial_phase TEXT,
            enrollment_date TEXT,
            cancer_type TEXT,
            disease_status TEXT,
            treatment_arm TEXT,
            patient_consent TEXT NOT NULL,
            consent_date TEXT,
            withdrawal_date TEXT,
            trial_status TEXT,
            source_system TEXT,
            record_date TEXT
        )
    """)
    
    # Define data generators
    cancer_types = [
        "Lung Cancer", "Colorectal Cancer", "Breast Cancer", "Prostate Cancer",
        "Pancreatic Cancer", "Ovarian Cancer", "Melanoma", "Lymphoma",
        "Leukemia", "Mesothelioma", "Bladder Cancer", "Renal Cancer"
    ]
    
    disease_status_options = [
        "Newly Diagnosed", "Recurrent", "Metastatic", "Remission",
        "Progressive", "Stable"
    ]
    
    treatment_arms = [
        "Control (Standard Care)", "Treatment A", "Treatment B",
        "Treatment C", "Combination A+B", "Combination B+C"
    ]
    
    trial_phases = ["Phase I", "Phase II", "Phase III", "Phase IV"]
    
    trial_statuses = ["Active", "Completed", "Withdrawn", "Suspended"]
    
    consent_flags = ["Y", "N"]
    
    # Generate mock data
    base_date = datetime(2020, 1, 1)
    
    rows = []
    for i in range(1, num_rows + 1):
        patient_sk = f"PT_{random.randint(1, 5000):06d}"
        trial_id = f"TRIAL_{random.randint(100000, 999999)}"
        trial_name = f"Oncology Study {random.randint(2020, 2025)}-{random.randint(1000, 9999)}"
        trial_phase = random.choice(trial_phases)
        
        # Enrollment date between 2020 and 2025
        enrollment_days_offset = random.randint(0, 1826)  # ~5 years
        enrollment_date = (base_date + timedelta(days=enrollment_days_offset)).strftime("%Y-%m-%d")
        
        cancer_type = random.choice(cancer_types)
        disease_status = random.choice(disease_status_options)
        treatment_arm = random.choice(treatment_arms)
        patient_consent = random.choice(consent_flags)
        
        # Consent date is after or at enrollment
        consent_days_offset = random.randint(enrollment_days_offset, enrollment_days_offset + 30)
        consent_date = (base_date + timedelta(days=consent_days_offset)).strftime("%Y-%m-%d") if patient_consent == "Y" else None
        
        # Withdrawal date (if applicable)
        withdrawal_date = None
        if patient_consent == "Y" and random.random() < 0.1:  # 10% withdrawal rate
            withdrawal_days_offset = random.randint(enrollment_days_offset + 30, enrollment_days_offset + 730)
            withdrawal_date = (base_date + timedelta(days=withdrawal_days_offset)).strftime("%Y-%m-%d")
        
        trial_status = random.choice(trial_statuses)
        source_system = "Cerner"
        record_date = datetime.now().strftime("%Y-%m-%d")
        
        rows.append((
            i, patient_sk, trial_id, trial_name, trial_phase, enrollment_date,
            cancer_type, disease_status, treatment_arm, patient_consent,
            consent_date, withdrawal_date, trial_status, source_system, record_date
        ))
    
    # Batch insert for better performance
    cursor.executemany("""
        INSERT INTO cerner_raw__cancer_clinical_trials
        (row_id, patient_sk, trial_id, trial_name, trial_phase, enrollment_date,
         cancer_type, disease_status, treatment_arm, patient_consent, consent_date,
         withdrawal_date, trial_status, source_system, record_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    
    conn.commit()
    
    # Verify
    cursor.execute("SELECT COUNT(*) FROM cerner_raw__cancer_clinical_trials")
    count = cursor.fetchone()[0]
    
    cursor.execute(
        "SELECT patient_consent, COUNT(*) as count FROM cerner_raw__cancer_clinical_trials GROUP BY patient_consent"
    )
    consent_breakdown = cursor.fetchall()
    
    conn.close()
    
    print(f"✓ Successfully created clinical trial table")
    print(f"  Total rows: {count}")
    print(f"  Consent breakdown:")
    for consent, cnt in consent_breakdown:
        percentage = (cnt / count * 100)
        print(f"    - Consent '{consent}': {cnt} rows ({percentage:.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a mock cancer clinical trial table in SQLite database"
    )
    parser.add_argument(
        "db_path",
        nargs="?",
        default="data/dwh/mock_feasibility_sqlite.db",
        help="Path to the SQLite database file (default: data/dwh/mock_feasibility_sqlite.db)"
    )
    parser.add_argument(
        "num_rows",
        nargs="?",
        type=int,
        default=10000,
        help="Number of rows to generate (default: 10000)"
    )
    
    args = parser.parse_args()
    create_clinical_trial_table(args.db_path, args.num_rows)
