from __future__ import annotations

import argparse
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence


DEFAULT_GENERATED_AT = "2026-03-17T16:12:34"


@dataclass(frozen=True)
class SimulationConfig:
    db_path: Path = Path("data/dwh/raw_demo.db")
    table_count: int = 50
    rows_per_table: int = 200
    seed: int = 42
    generated_at: datetime = datetime.fromisoformat(DEFAULT_GENERATED_AT)


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def random_date(
    rng: random.Random,
    generated_at: datetime,
    days_back: int = 365 * 5,
) -> str:
    delta = rng.randint(0, days_back)
    return (generated_at - timedelta(days=delta)).strftime("%Y-%m-%d")


def maybe_missing(rng: random.Random, value: Any, probability: float) -> Any:
    if rng.random() < probability:
        return None
    return value


def create_cancer_inpatient_core(
    conn: sqlite3.Connection,
    rng: random.Random,
    rows_per_table: int,
    generated_at: datetime,
) -> tuple[int, list[str]]:
    load_ts = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
    patient_count = max(120, rows_per_table)
    patient_sks = [f"PT{idx:06d}" for idx in range(1, patient_count + 1)]
    spells: list[tuple[str, str, str]] = []

    conn.execute(
        """
        CREATE TABLE raw_cancer_patients (
            patient_sk TEXT PRIMARY KEY,
            pseudo_nhs_id TEXT,
            sex TEXT,
            YOB INTEGER,
            ethnicity_group TEXT,
            postcode_lsoa TEXT,
            smoking_status TEXT,
            bmi REAL,
            charlson_index INTEGER,
            reg_dt TEXT,
            dod TEXT,
            is_deceased INTEGER,
            load_ts TEXT
        )
        """
    )
    patients_rows: list[tuple[Any, ...]] = []
    for patient_sk in patient_sks:
        is_deceased = 1 if rng.random() < 0.14 else 0
        registration_date = random_date(rng, generated_at, days_back=365 * 8)
        death_date = (
            random_date(rng, generated_at, days_back=365 * 4)
            if is_deceased
            else None
        )
        patients_rows.append(
            (
                patient_sk,
                f"ANON{rng.randint(10000000, 99999999)}",
                rng.choice(["F", "M", "X"]),
                rng.randint(1935, 2005),
                rng.choice(
                    ["white", "asian", "black", "mixed", "other", "unknown"]
                ),
                f"LSOA{rng.randint(10000, 99999)}",
                rng.choice(["never", "former", "current", "unknown"]),
                round(max(15.5, min(48.0, rng.gauss(27.0, 5.2))), 1),
                rng.randint(0, 9),
                registration_date,
                death_date,
                is_deceased,
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_cancer_patients
            (patient_sk, pseudo_nhs_id, sex, YOB, ethnicity_group, postcode_lsoa,
            smoking_status, bmi, charlson_index, reg_dt, dod, is_deceased, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        patients_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_cancer_diagnoses (
            diagnosis_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            dx_date TEXT,
            TumourSite TEXT,
            ICD10_code TEXT,
            Clinical_Stage TEXT,
            morph_icdo3 TEXT,
            tnm_t TEXT,
            tnm_n TEXT,
            tnm_m TEXT,
            metastatic_flag INTEGER,
            mdt_pathway TEXT,
            load_ts TEXT
        )
        """
    )
    dx_rows: list[tuple[Any, ...]] = []
    cancer_sites = [
        "breast",
        "lung",
        "colorectal",
        "prostate",
        "ovarian",
        "haematology",
    ]
    for idx in range(int(patient_count * 1.2)):
        metastatic = 1 if rng.random() < 0.25 else 0
        dx_rows.append(
            (
                f"DX{idx + 1:07d}",
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 6),
                rng.choice(cancer_sites),
                rng.choice(["C50", "C34", "C18", "C61", "C56", "C91"]),
                rng.choice(["I", "II", "III", "IV", "unknown"]),
                f"M{rng.randint(8000, 8999)}",
                rng.choice(["T1", "T2", "T3", "T4"]),
                rng.choice(["N0", "N1", "N2", "N3"]),
                "M1" if metastatic else "M0",
                metastatic,
                rng.choice(["rapid", "standard", "urgent"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_cancer_diagnoses
            (diagnosis_sk, patient_sk, dx_date, TumourSite, ICD10_code, Clinical_Stage,
            morph_icdo3, tnm_t, tnm_n, tnm_m, metastatic_flag, mdt_pathway, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        dx_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_inpatient_spells (
            spell_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            adm_date TEXT,
            dis_date TEXT,
            LOS_days INTEGER,
            Adm_Method TEXT,
            discharge_destination TEXT,
            ward_specialty TEXT,
            hrg_code TEXT,
            critical_care_flag INTEGER,
            readmission_30d_flag INTEGER,
            load_ts TEXT
        )
        """
    )
    spell_rows: list[tuple[Any, ...]] = []
    for idx in range(int(patient_count * 1.8)):
        admission_date = random_date(rng, generated_at, days_back=365 * 3)
        los = max(1, int(abs(rng.gauss(6, 4))))
        discharge_date = (
            datetime.strptime(admission_date, "%Y-%m-%d") + timedelta(days=los)
        ).strftime("%Y-%m-%d")
        spell_sk = f"SP{idx + 1:07d}"
        patient_sk = rng.choice(patient_sks)
        spell_rows.append(
            (
                spell_sk,
                patient_sk,
                admission_date,
                discharge_date,
                los,
                rng.choice(["elective", "emergency", "transfer"]),
                rng.choice(["home", "rehab", "care_home", "deceased"]),
                rng.choice(
                    ["oncology", "haematology", "general_medicine", "surgery"]
                ),
                f"HRG{rng.randint(100, 999)}",
                1 if rng.random() < 0.18 else 0,
                1 if rng.random() < 0.15 else 0,
                load_ts,
            )
        )
        spells.append((spell_sk, patient_sk, admission_date))
    conn.executemany(
        """
        INSERT INTO raw_inpatient_spells
            (spell_sk, patient_sk, adm_date, dis_date, LOS_days,
            Adm_Method, discharge_destination, ward_specialty, hrg_code,
            critical_care_flag, readmission_30d_flag, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        spell_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_inpatient_episodes (
            episode_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            ep_start_dt TEXT,
            ep_end_dt TEXT,
            cons_code TEXT,
            proc_OPCS4 TEXT,
            Dx_ICD10 TEXT,
            palliative_care_flag INTEGER,
            cost_GBP REAL,
            load_ts TEXT
        )
        """
    )
    episode_rows: list[tuple[Any, ...]] = []
    for idx, (spell_sk, patient_sk, admission_date) in enumerate(spells):
        episode_count = rng.randint(1, 3)
        base = datetime.strptime(admission_date, "%Y-%m-%d")
        for ep in range(episode_count):
            start = base + timedelta(days=ep * 2)
            end = start + timedelta(days=rng.randint(1, 3))
            episode_rows.append(
                (
                    f"EP{idx + 1:06d}{ep + 1}",
                    spell_sk,
                    patient_sk,
                    start.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d"),
                    f"C{rng.randint(100, 999)}",
                    rng.choice(["X65.1", "Y42.3", "W37.4", "A12.8"]),
                    rng.choice(["C50", "C34", "C18", "D64", "I10"]),
                    1 if rng.random() < 0.10 else 0,
                    round(max(420.0, rng.gauss(2600.0, 900.0)), 2),
                    load_ts,
                )
            )
    conn.executemany(
        """
        INSERT INTO raw_inpatient_episodes
            (episode_sk, spell_sk, patient_sk, ep_start_dt, ep_end_dt,
            cons_code, proc_OPCS4, Dx_ICD10,
            palliative_care_flag, cost_GBP, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        episode_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_cancer_treatments (
            treatment_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            Tx_start_date TEXT,
            Tx_modality TEXT,
            regimen_code TEXT,
            cycle_number INTEGER,
            dose_mg REAL,
            intent TEXT,
            Tx_response TEXT,
            toxicity_grade INTEGER,
            load_ts TEXT
        )
        """
    )
    tx_rows: list[tuple[Any, ...]] = []
    for idx in range(int(patient_count * 1.6)):
        tx_rows.append(
            (
                f"TX{idx + 1:07d}",
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 3),
                rng.choice(
                    [
                        "chemotherapy",
                        "radiotherapy",
                        "immunotherapy",
                        "surgery",
                        "hormonal",
                    ]
                ),
                rng.choice(["FOLFOX", "CARBO-TAXOL", "R-CHOP", "PEMBRO", "LETRO"]),
                rng.randint(1, 8),
                maybe_missing(
                    rng,
                    round(max(5.0, rng.gauss(180.0, 65.0)), 2),
                    0.08,
                ),
                rng.choice(["curative", "adjuvant", "neoadjuvant", "palliative"]),
                rng.choice(
                    ["complete", "partial", "stable", "progressive", "unknown"]
                ),
                rng.randint(0, 4),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_cancer_treatments
            (treatment_sk, patient_sk, Tx_start_date, Tx_modality, regimen_code,
            cycle_number, dose_mg, intent, Tx_response, toxicity_grade, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tx_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_lab_results (
            lab_result_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            request_dt TEXT,
            test_name TEXT,
            result_numeric REAL,
            unit TEXT,
            reference_low REAL,
            reference_high REAL,
            abnormal_flag INTEGER,
            sys_source TEXT,
            load_ts TEXT
        )
        """
    )
    lab_defs = [
        ("Hb", "g/L", 120.0, 170.0),
        ("WCC", "10^9/L", 4.0, 11.0),
        ("PLT", "10^9/L", 150.0, 450.0),
        ("Cr", "umol/L", 45.0, 110.0),
        ("Alb", "g/L", 35.0, 50.0),
    ]
    lab_rows: list[tuple[Any, ...]] = []
    for idx in range(int(patient_count * 3.5)):
        test_name, unit, low, high = rng.choice(lab_defs)
        value = round(rng.uniform(low * 0.5, high * 1.4), 2)
        abnormal = 1 if value < low or value > high else 0
        lab_rows.append(
            (
                f"LB{idx + 1:08d}",
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 3),
                test_name,
                maybe_missing(rng, value, 0.03),
                unit,
                low,
                high,
                abnormal,
                rng.choice(["lims", "epr"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_lab_results
            (lab_result_sk, patient_sk, request_dt, test_name, result_numeric, unit,
            reference_low, reference_high, abnormal_flag, sys_source, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        lab_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_cancer_outcomes (
            outcome_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            outcome_date TEXT,
            OS_days INTEGER,
            PFS_days INTEGER,
            recurrence_flag INTEGER,
            mortality_90d_flag INTEGER,
            EA_90d_flag INTEGER,
            proms_score REAL,
            load_ts TEXT
        )
        """
    )
    outcome_rows: list[tuple[Any, ...]] = []
    for idx in range(int(patient_count * 0.9)):
        os_days = max(20, int(abs(rng.gauss(760, 420))))
        pfs_days = max(10, min(os_days, int(abs(rng.gauss(420, 250)))))
        outcome_rows.append(
            (
                f"OC{idx + 1:07d}",
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 2),
                os_days,
                pfs_days,
                1 if rng.random() < 0.28 else 0,
                1 if rng.random() < 0.12 else 0,
                1 if rng.random() < 0.22 else 0,
                round(rng.uniform(30.0, 95.0), 1),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_cancer_outcomes
            (outcome_sk, patient_sk, outcome_date, OS_days, PFS_days,
            recurrence_flag, mortality_90d_flag, EA_90d_flag, proms_score, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        outcome_rows,
    )

    core_tables = [
        "raw_cancer_patients",
        "raw_cancer_diagnoses",
        "raw_inpatient_spells",
        "raw_inpatient_episodes",
        "raw_cancer_treatments",
        "raw_lab_results",
        "raw_cancer_outcomes",
    ]
    return len(core_tables), patient_sks


def create_supplemental_table(
    conn: sqlite3.Connection,
    rng: random.Random,
    table_name: str,
    patient_sks: list[str],
    rows_per_table: int,
    kind: str,
    generated_at: datetime,
) -> None:
    load_ts = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
    if kind == "obs":
        conn.execute(
            f"""
            CREATE TABLE {table_name} (
                obs_sk TEXT PRIMARY KEY,
                patient_sk TEXT,
                obs_dt TEXT,
                HR INTEGER,
                SBP INTEGER,
                RR INTEGER,
                spo2 REAL,
                temp_C REAL,
                NEWS2 INTEGER,
                ward_loc TEXT,
                load_ts TEXT
            )
            """
        )
        rows: list[tuple[Any, ...]] = []
        for idx in range(rows_per_table):
            rows.append(
                (
                    f"OBS{idx + 1:08d}",
                    rng.choice(patient_sks),
                    f"{random_date(rng, generated_at, days_back=365 * 2)}T"
                    f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                    int(max(38, min(150, rng.gauss(82, 18)))),
                    int(max(75, min(220, rng.gauss(122, 22)))),
                    int(max(8, min(40, rng.gauss(18, 5)))),
                    round(max(76.0, min(100.0, rng.gauss(95.5, 2.6))), 1),
                    round(max(34.5, min(41.5, rng.gauss(36.9, 0.8))), 1),
                    rng.randint(0, 12),
                    rng.choice(["ward_a", "ward_b", "icu", "oncology_day_unit"]),
                    load_ts,
                )
            )
        conn.executemany(
            f"""
            INSERT INTO {table_name}
                (obs_sk, patient_sk, obs_dt, HR, SBP,
                RR, spo2, temp_C, NEWS2, ward_loc, load_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        return

    conn.execute(
        f"""
        CREATE TABLE {table_name} (
            record_sk TEXT PRIMARY KEY,
            patient_sk TEXT,
            extract_dt TEXT,
            registry_source TEXT,
            cwt_62d_flag INTEGER,
            mdt_disc_flag INTEGER,
            trial_elig_flag INTEGER,
            travel_dist_km REAL,
            IMD_decile INTEGER,
            dq_status TEXT,
            load_ts TEXT
        )
        """
    )
    rows: list[tuple[Any, ...]] = []
    for idx in range(rows_per_table):
        rows.append(
            (
                f"RG{idx + 1:08d}",
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 2),
                rng.choice(
                    ["regional_registry", "trust_dataset", "national_audit"]
                ),
                1 if rng.random() < 0.78 else 0,
                1 if rng.random() < 0.90 else 0,
                1 if rng.random() < 0.16 else 0,
                round(max(0.5, abs(rng.gauss(11.0, 7.5))), 1),
                rng.randint(1, 10),
                rng.choice(["complete", "partial", "needs_review"]),
                load_ts,
            )
        )
    conn.executemany(
        f"""
        INSERT INTO {table_name}
            (record_sk, patient_sk, extract_dt, registry_source, cwt_62d_flag,
            mdt_disc_flag, trial_elig_flag, travel_dist_km,
            IMD_decile, dq_status, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def create_diverse_cancer_resource_tables(
    conn: sqlite3.Connection,
    rng: random.Random,
    patient_sks: list[str],
    rows_per_table: int,
    generated_at: datetime,
) -> int:
    load_ts = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
    case_refs = [
        f"CASE{idx:07d}" for idx in range(1, max(80, rows_per_table) + 1)
    ]

    conn.execute(
        """
        CREATE TABLE raw_pathology_reports (
            pathology_report_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            spec_date TEXT,
            specimen_type TEXT,
            histo_result TEXT,
            grade TEXT,
            er_status TEXT,
            pr_status TEXT,
            her2_status TEXT,
            src_system TEXT,
            load_ts TEXT
        )
        """
    )
    path_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 1.2)):
        path_rows.append(
            (
                f"PATH{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 4),
                rng.choice(["biopsy", "resection", "cytology", "bone_marrow"]),
                rng.choice(
                    [
                        "adenocarcinoma",
                        "squamous",
                        "ductal",
                        "lymphoma",
                        "benign",
                        "atypia",
                    ]
                ),
                rng.choice(["G1", "G2", "G3", "unknown"]),
                rng.choice(["positive", "negative", "equivocal", "unknown"]),
                rng.choice(["positive", "negative", "equivocal", "unknown"]),
                rng.choice(["positive", "negative", "equivocal", "unknown"]),
                rng.choice(["path_lims", "regional_pathology_hub"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_pathology_reports
            (pathology_report_sk, case_ref, patient_sk, spec_date, specimen_type, histo_result,
            grade, er_status, pr_status, her2_status, src_system, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        path_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_imaging_reports (
            imaging_report_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            img_date TEXT,
            modality TEXT,
            body_site TEXT,
            RECIST_resp TEXT,
            suv_max REAL,
            rad_report_impression TEXT,
            pacs_src TEXT,
            load_ts TEXT
        )
        """
    )
    img_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 1.4)):
        img_rows.append(
            (
                f"IMG{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 4),
                rng.choice(["CT", "MRI", "PET-CT", "XR"]),
                rng.choice(["thorax", "abdomen", "pelvis", "brain", "whole_body"]),
                rng.choice(["CR", "PR", "SD", "PD", "not_assessed"]),
                maybe_missing(
                    rng,
                    round(max(0.5, rng.gauss(5.5, 3.2)), 2),
                    0.18,
                ),
                rng.choice(
                    [
                        "no_progression",
                        "possible_progression",
                        "new_lesion",
                        "treatment_response",
                    ]
                ),
                rng.choice(["pacs_a", "pacs_b"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_imaging_reports
            (imaging_report_sk, case_ref, patient_sk, img_date, modality, body_site,
            RECIST_resp, suv_max, rad_report_impression, pacs_src, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        img_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_genomic_variants (
            genomic_result_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            ngs_date TEXT,
            gene_symbol TEXT,
            variant_coding TEXT,
            ClinVar_class TEXT,
            TMB REAL,
            MSI TEXT,
            actionability_tier TEXT,
            seq_lab TEXT,
            load_ts TEXT
        )
        """
    )
    genes = [
        "EGFR",
        "KRAS",
        "BRAF",
        "TP53",
        "PIK3CA",
        "BRCA1",
        "BRCA2",
        "ALK",
        "ROS1",
    ]
    gen_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 0.9)):
        gen_rows.append(
            (
                f"GEN{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 4),
                rng.choice(genes),
                f"c.{rng.randint(50, 900)}{rng.choice(['A>T', 'G>C', 'del', 'ins'])}",
                rng.choice(["pathogenic", "likely_pathogenic", "vus", "benign"]),
                maybe_missing(
                    rng,
                    round(max(0.0, rng.gauss(8.0, 5.5)), 2),
                    0.12,
                ),
                rng.choice(["MSI-H", "MSS", "unknown"]),
                rng.choice(["tier_1", "tier_2", "tier_3", "none"]),
                rng.choice(["molecular_lab_a", "molecular_lab_b"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_genomic_variants
            (genomic_result_sk, case_ref, patient_sk, ngs_date, gene_symbol, variant_coding,
            ClinVar_class, TMB, MSI, actionability_tier,
            seq_lab, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        gen_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_radiotherapy_fractions (
            rt_fraction_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            fx_date TEXT,
            treatment_site TEXT,
            fraction_number INTEGER,
            presc_dose_Gy REAL,
            deliv_dose_Gy REAL,
            machine_id TEXT,
            attend_status TEXT,
            load_ts TEXT
        )
        """
    )
    rt_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 1.8)):
        prescribed = round(max(1.8, rng.gauss(2.0, 0.35)), 2)
        delivered = maybe_missing(
            rng,
            round(max(0.0, prescribed + rng.uniform(-0.12, 0.08)), 2),
            0.03,
        )
        rt_rows.append(
            (
                f"RT{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 3),
                rng.choice(["breast", "lung", "pelvis", "brain", "spine"]),
                rng.randint(1, 35),
                prescribed,
                delivered,
                f"LINAC-{rng.randint(1, 6)}",
                rng.choice(["attended", "dna", "cancelled", "rescheduled"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_radiotherapy_fractions
            (rt_fraction_sk, case_ref, patient_sk, fx_date, treatment_site,
            fraction_number, presc_dose_Gy, deliv_dose_Gy, machine_id,
            attend_status, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rt_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_systemic_therapy_orders (
            order_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            ord_date TEXT,
            drug_name TEXT,
            regimen_code TEXT,
            planned_cycles INTEGER,
            cycle_day INTEGER,
            plan_dose_mg REAL,
            admin_flag INTEGER,
            px_system TEXT,
            load_ts TEXT
        )
        """
    )
    drugs = [
        "pembrolizumab",
        "trastuzumab",
        "carboplatin",
        "paclitaxel",
        "rituximab",
        "docetaxel",
    ]
    st_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 1.5)):
        st_rows.append(
            (
                f"STO{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 3),
                rng.choice(drugs),
                rng.choice(
                    ["FOLFOX", "CARBO-TAXOL", "R-CHOP", "CAPOX", "PEMBRO_MONO"]
                ),
                rng.randint(1, 8),
                rng.randint(1, 28),
                round(max(10.0, rng.gauss(220.0, 75.0)), 2),
                1 if rng.random() < 0.88 else 0,
                rng.choice(["chemo_epma", "oncology_cpoe", "legacy_rx"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_systemic_therapy_orders
            (order_sk, case_ref, patient_sk, ord_date, drug_name, regimen_code,
            planned_cycles, cycle_day, plan_dose_mg, admin_flag, px_system, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        st_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_mdt_decisions (
            mdt_decision_sk TEXT PRIMARY KEY,
            case_ref TEXT,
            patient_sk TEXT,
            mdt_date TEXT,
            site_group TEXT,
            rec_plan TEXT,
            priority_level TEXT,
            trial_eligib_flag INTEGER,
            Tx_intent TEXT,
            mdt_src TEXT,
            load_ts TEXT
        )
        """
    )
    mdt_rows: list[tuple[Any, ...]] = []
    for idx in range(int(rows_per_table * 1.1)):
        mdt_rows.append(
            (
                f"MDT{idx + 1:08d}",
                rng.choice(case_refs),
                rng.choice(patient_sks),
                random_date(rng, generated_at, days_back=365 * 3),
                rng.choice(
                    ["breast", "lung", "colorectal", "urology", "haematology"]
                ),
                rng.choice(
                    [
                        "surgery_first",
                        "systemic_then_review",
                        "radiotherapy",
                        "supportive_care",
                    ]
                ),
                rng.choice(["urgent", "routine", "deferred"]),
                1 if rng.random() < 0.24 else 0,
                rng.choice(["curative", "non_curative", "palliative"]),
                rng.choice(["mdt_system_a", "mdt_system_b"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_mdt_decisions
            (mdt_decision_sk, case_ref, patient_sk, mdt_date, site_group, rec_plan,
            priority_level, trial_eligib_flag, Tx_intent, mdt_src, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        mdt_rows,
    )

    return 6


def create_vte_model_tables(
    conn: sqlite3.Connection,
    rng: random.Random,
    rows_per_table: int,
    generated_at: datetime,
) -> int:
    load_ts = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
    spell_rows = conn.execute(
        """
        SELECT spell_sk, patient_sk, adm_date
        FROM raw_inpatient_spells
        """
    ).fetchall()

    conn.execute(
        """
        CREATE TABLE raw_vte_risk_assessments (
            vte_assess_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            assess_dt TEXT,
            padua_score INTEGER,
            caprini_score INTEGER,
            vte_high_risk_flag INTEGER,
            mech_px_flag INTEGER,
            pharm_px_rx TEXT,
            bleed_risk_flag INTEGER,
            src_sys TEXT,
            load_ts TEXT
        )
        """
    )
    assess_rows: list[tuple[Any, ...]] = []
    for idx in range(max(rows_per_table, int(len(spell_rows) * 1.1))):
        spell_sk, patient_sk, adm_date = rng.choice(spell_rows)
        assess_rows.append(
            (
                f"VTEA{idx + 1:08d}",
                spell_sk,
                patient_sk,
                f"{adm_date}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                rng.randint(0, 8),
                rng.randint(0, 12),
                1 if rng.random() < 0.34 else 0,
                1 if rng.random() < 0.28 else 0,
                rng.choice(["lmwh", "doac", "ufh", "none"]),
                1 if rng.random() < 0.14 else 0,
                rng.choice(["epr", "nursing_obs", "ward_clerking"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_vte_risk_assessments
            (vte_assess_sk, spell_sk, patient_sk, assess_dt, padua_score,
            caprini_score, vte_high_risk_flag, mech_px_flag, pharm_px_rx,
            bleed_risk_flag, src_sys, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        assess_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_vte_events (
            vte_event_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            event_dt TEXT,
            vte_type TEXT,
            anatom_site TEXT,
            confirm_img_flag INTEGER,
            anticoag_start_dt TEXT,
            ha_vte_flag INTEGER,
            icd10_vte TEXT,
            outcome_30d TEXT,
            load_ts TEXT
        )
        """
    )
    event_rows: list[tuple[Any, ...]] = []
    for idx in range(max(20, int(rows_per_table * 0.35))):
        spell_sk, patient_sk, _adm_date = rng.choice(spell_rows)
        ev_date = random_date(rng, generated_at, days_back=365 * 2)
        event_rows.append(
            (
                f"VTEE{idx + 1:08d}",
                spell_sk,
                patient_sk,
                ev_date,
                rng.choice(["dvt", "pe", "line_related", "svt"]),
                rng.choice(["proximal_leg", "distal_leg", "pulmonary", "upper_limb"]),
                1 if rng.random() < 0.92 else 0,
                maybe_missing(rng, ev_date, 0.18),
                1 if rng.random() < 0.58 else 0,
                rng.choice(["I26", "I80", "I82", "O22"]),
                rng.choice(
                    ["resolved", "ongoing_treatment", "recurrent", "deceased"]
                ),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_vte_events
            (vte_event_sk, spell_sk, patient_sk, event_dt, vte_type,
            anatom_site, confirm_img_flag, anticoag_start_dt, ha_vte_flag,
            icd10_vte, outcome_30d, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        event_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_vte_prophylaxis_admin (
            vte_px_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            admin_dt TEXT,
            px_type TEXT,
            px_drug TEXT,
            dose_mg REAL,
            missed_dose_flag INTEGER,
            contraind_flag INTEGER,
            reason_not_given TEXT,
            load_ts TEXT
        )
        """
    )
    px_rows: list[tuple[Any, ...]] = []
    for idx in range(max(rows_per_table, int(len(spell_rows) * 1.4))):
        spell_sk, patient_sk, adm_date = rng.choice(spell_rows)
        px_rows.append(
            (
                f"VTEP{idx + 1:08d}",
                spell_sk,
                patient_sk,
                f"{adm_date}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                rng.choice(["pharmacologic", "mechanical"]),
                rng.choice(["enoxaparin", "heparin", "apixaban", "none"]),
                maybe_missing(
                    rng,
                    round(max(0.0, rng.gauss(25.0, 15.0)), 2),
                    0.22,
                ),
                1 if rng.random() < 0.09 else 0,
                1 if rng.random() < 0.12 else 0,
                rng.choice(
                    [
                        "none",
                        "active_bleed",
                        "platelets_low",
                        "procedure",
                        "patient_refused",
                    ]
                ),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_vte_prophylaxis_admin
            (vte_px_sk, spell_sk, patient_sk, admin_dt, px_type, px_drug,
            dose_mg, missed_dose_flag, contraind_flag, reason_not_given, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        px_rows,
    )

    return 3


def create_falls_model_tables(
    conn: sqlite3.Connection,
    rng: random.Random,
    rows_per_table: int,
    generated_at: datetime,
) -> int:
    load_ts = generated_at.strftime("%Y-%m-%dT%H:%M:%S")
    spell_rows = conn.execute(
        """
        SELECT spell_sk, patient_sk, adm_date
        FROM raw_inpatient_spells
        """
    ).fetchall()

    conn.execute(
        """
        CREATE TABLE raw_falls_risk_screenings (
            falls_screen_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            screen_dt TEXT,
            morse_score INTEGER,
            mobility_lvl TEXT,
            cognition_impair_flag INTEGER,
            prior_fall_6m_flag INTEGER,
            falls_high_risk_flag INTEGER,
            prevent_bundle_flag INTEGER,
            src_sys TEXT,
            load_ts TEXT
        )
        """
    )
    screen_rows: list[tuple[Any, ...]] = []
    for idx in range(max(rows_per_table, int(len(spell_rows) * 1.3))):
        spell_sk, patient_sk, adm_date = rng.choice(spell_rows)
        screen_rows.append(
            (
                f"FLS{idx + 1:08d}",
                spell_sk,
                patient_sk,
                f"{adm_date}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                rng.randint(0, 125),
                rng.choice(["independent", "assisted", "frame", "bedbound"]),
                1 if rng.random() < 0.26 else 0,
                1 if rng.random() < 0.21 else 0,
                1 if rng.random() < 0.31 else 0,
                1 if rng.random() < 0.68 else 0,
                rng.choice(["epr", "nursing_obs", "therapy_assessment"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_falls_risk_screenings
            (falls_screen_sk, spell_sk, patient_sk, screen_dt, morse_score,
            mobility_lvl, cognition_impair_flag, prior_fall_6m_flag,
            falls_high_risk_flag, prevent_bundle_flag, src_sys, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        screen_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_falls_incidents (
            fall_event_sk TEXT PRIMARY KEY,
            spell_sk TEXT,
            patient_sk TEXT,
            fall_dt TEXT,
            fall_loc TEXT,
            unwitnessed_flag INTEGER,
            head_strike_flag INTEGER,
            injury_severity TEXT,
            post_fall_obs_flag INTEGER,
            transfer_to_ed_flag INTEGER,
            load_ts TEXT
        )
        """
    )
    incident_rows: list[tuple[Any, ...]] = []
    for idx in range(max(18, int(rows_per_table * 0.28))):
        spell_sk, patient_sk, adm_date = rng.choice(spell_rows)
        incident_rows.append(
            (
                f"FLI{idx + 1:08d}",
                spell_sk,
                patient_sk,
                f"{adm_date}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
                rng.choice(
                    ["bedspace", "bathroom", "corridor", "therapy_gym", "stairs"]
                ),
                1 if rng.random() < 0.46 else 0,
                1 if rng.random() < 0.19 else 0,
                rng.choice(["none", "minor", "moderate", "severe"]),
                1 if rng.random() < 0.84 else 0,
                1 if rng.random() < 0.09 else 0,
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_falls_incidents
            (fall_event_sk, spell_sk, patient_sk, fall_dt, fall_loc,
            unwitnessed_flag, head_strike_flag, injury_severity,
            post_fall_obs_flag, transfer_to_ed_flag, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        incident_rows,
    )

    conn.execute(
        """
        CREATE TABLE raw_falls_post_event_reviews (
            fall_review_sk TEXT PRIMARY KEY,
            fall_event_sk TEXT,
            patient_sk TEXT,
            review_dt TEXT,
            med_review_flag INTEGER,
            physio_review_flag INTEGER,
            env_hazard_flag INTEGER,
            repeat_fall_7d_flag INTEGER,
            action_plan TEXT,
            reviewer_role TEXT,
            load_ts TEXT
        )
        """
    )
    review_rows: list[tuple[Any, ...]] = []
    for idx in range(max(18, int(rows_per_table * 0.26))):
        review_rows.append(
            (
                f"FLR{idx + 1:08d}",
                f"FLI{rng.randint(1, max(18, int(rows_per_table * 0.28))):08d}",
                rng.choice([row[1] for row in spell_rows]),
                random_date(rng, generated_at, days_back=365 * 2),
                1 if rng.random() < 0.86 else 0,
                1 if rng.random() < 0.72 else 0,
                1 if rng.random() < 0.33 else 0,
                1 if rng.random() < 0.15 else 0,
                rng.choice(
                    [
                        "sensor_alarm",
                        "low_bed",
                        "toileting_rounds",
                        "meds_optimised",
                        "physio_program",
                    ]
                ),
                rng.choice(["nurse", "doctor", "physio", "matron"]),
                load_ts,
            )
        )
    conn.executemany(
        """
        INSERT INTO raw_falls_post_event_reviews
            (fall_review_sk, fall_event_sk, patient_sk, review_dt,
            med_review_flag, physio_review_flag, env_hazard_flag,
            repeat_fall_7d_flag, action_plan, reviewer_role, load_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        review_rows,
    )

    return 3


def simulate_local_raw_db(config: SimulationConfig) -> dict[str, Any]:
    ensure_directory(config.db_path.parent)
    if config.db_path.exists():
        config.db_path.unlink()

    rng = random.Random(config.seed)
    start = time.time()

    conn = connect_db(config.db_path)
    created_tables = 0

    try:
        core_count, patient_sks = create_cancer_inpatient_core(
            conn,
            rng,
            config.rows_per_table,
            config.generated_at,
        )
        created_tables += core_count
        created_tables += create_diverse_cancer_resource_tables(
            conn,
            rng,
            patient_sks,
            config.rows_per_table,
            config.generated_at,
        )
        created_tables += create_vte_model_tables(
            conn,
            rng,
            config.rows_per_table,
            config.generated_at,
        )
        created_tables += create_falls_model_tables(
            conn,
            rng,
            config.rows_per_table,
            config.generated_at,
        )

        supplement_idx = 0
        while created_tables < config.table_count:
            kind = "obs" if supplement_idx % 2 == 0 else "registry"
            table_name = (
                f"raw_{'inpatient_observations' if kind == 'obs' else 'cancer_registry'}_"
                f"{supplement_idx:04d}"
            )
            create_supplemental_table(
                conn,
                rng,
                table_name,
                patient_sks,
                config.rows_per_table,
                kind,
                config.generated_at,
            )
            created_tables += 1
            supplement_idx += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "database": str(config.db_path),
        "tables_created": created_tables,
        "rows_per_table": config.rows_per_table,
        "duration_seconds": round(time.time() - start, 2),
        "seed": config.seed,
        "generated_at": config.generated_at.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def parse_generated_at(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "generated-at must be ISO-8601, e.g. 2026-03-17T16:12:34"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the synthetic raw_demo.db source database."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=SimulationConfig.db_path,
        help="Target SQLite database path.",
    )
    parser.add_argument(
        "--tables",
        type=int,
        default=SimulationConfig.table_count,
        help="Total number of raw tables to create.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=SimulationConfig.rows_per_table,
        help="Base row count used for generated tables.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=SimulationConfig.seed,
        help="Deterministic RNG seed.",
    )
    parser.add_argument(
        "--generated-at",
        type=parse_generated_at,
        default=SimulationConfig.generated_at,
        help=(
            "Anchor timestamp used for load_ts and generated dates. "
            "Defaults to the enriched historical source DB timestamp."
        ),
    )
    return parser


def config_from_args(args: argparse.Namespace) -> SimulationConfig:
    return SimulationConfig(
        db_path=args.db,
        table_count=args.tables,
        rows_per_table=args.rows,
        seed=args.seed,
        generated_at=args.generated_at,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = simulate_local_raw_db(config_from_args(args))
    print(f"Created {result['database']}")
    print(f"Tables: {result['tables_created']}")
    print(f"Rows/table: {result['rows_per_table']}")
    print(f"Seed: {result['seed']}")
    print(f"Generated at: {result['generated_at']}")
    print(f"Duration: {result['duration_seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
