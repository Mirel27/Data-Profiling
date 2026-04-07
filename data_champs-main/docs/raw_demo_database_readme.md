## raw_demo.db README

### Purpose

`data/dwh/raw_demo.db` is a synthetic, anonymised, offline SQLite database designed for hackathon demos of data feasibility assessment across large raw estates.

The dataset is intentionally realistic for oncology and inpatient analytics, and includes cross-resource overlap to mimic real-world integration complexity.

### Key characteristics

- Anonymised patient records (`patient_sk`, `pseudo_nhs_id`)
- Cancer pathway data (diagnosis, treatment, outcomes)
- Inpatient activity (spells, episodes, observations)
- Additional safety models (VTE risk/events/prophylaxis and Falls risk/incidents/reviews)
- Diverse source resources (pathology, imaging, genomics, MDT, systemic therapy)
- Intentional overlap across `patient_sk` and `case_ref`
- **Heterogeneous column naming** — each source system uses its own naming conventions, including abbreviations, mixed case, and clinical shorthand, as encountered in real hospital data estates
- Built-in data quality variability (missing values, heterogeneous source systems)

### Column naming conventions

Columns across tables intentionally differ in naming style to reflect real-world variation across hospital source systems. Below are the clinically-abbreviated or renamed columns per table.

| Table | Column | Clinical meaning |
|---|---|---|
| `raw_cancer_patients` | `YOB` | Year of birth |
| `raw_cancer_patients` | `reg_dt` | Registration date |
| `raw_cancer_patients` | `dod` | Date of death |
| `raw_cancer_diagnoses` | `dx_date` | Diagnosis date |
| `raw_cancer_diagnoses` | `TumourSite` | Cancer site (mixed-case registry style) |
| `raw_cancer_diagnoses` | `ICD10_code` | ICD-10 diagnosis code |
| `raw_cancer_diagnoses` | `Clinical_Stage` | Stage group (I–IV) |
| `raw_cancer_diagnoses` | `morph_icdo3` | Morphology code (ICD-O-3) |
| `raw_inpatient_spells` | `adm_date` | Admission date |
| `raw_inpatient_spells` | `dis_date` | Discharge date |
| `raw_inpatient_spells` | `LOS_days` | Length of stay (days) |
| `raw_inpatient_spells` | `Adm_Method` | Admission method |
| `raw_inpatient_episodes` | `ep_start_dt` | Episode start date |
| `raw_inpatient_episodes` | `ep_end_dt` | Episode end date |
| `raw_inpatient_episodes` | `cons_code` | Consultant code |
| `raw_inpatient_episodes` | `proc_OPCS4` | Primary procedure (OPCS-4 code) |
| `raw_inpatient_episodes` | `Dx_ICD10` | Primary diagnosis (ICD-10) |
| `raw_inpatient_episodes` | `cost_GBP` | Episode cost in GBP |
| `raw_cancer_treatments` | `Tx_start_date` | Treatment start date |
| `raw_cancer_treatments` | `Tx_modality` | Treatment modality |
| `raw_cancer_treatments` | `Tx_response` | Treatment response |
| `raw_lab_results` | `request_dt` | Sample/request date |
| `raw_lab_results` | `result_numeric` | Numeric result value |
| `raw_lab_results` | `sys_source` | Source system (e.g. LIMS, EPR) |
| `raw_lab_results` | `Hb`, `WCC`, `PLT`, `Cr`, `Alb` | Haemoglobin, White cell count, Platelets, Creatinine, Albumin |
| `raw_cancer_outcomes` | `OS_days` | Overall survival in days |
| `raw_cancer_outcomes` | `PFS_days` | Progression-free survival in days |
| `raw_cancer_outcomes` | `EA_90d_flag` | Emergency admission within 90 days flag |
| `raw_pathology_reports` | `spec_date` | Specimen date |
| `raw_pathology_reports` | `histo_result` | Histology result |
| `raw_pathology_reports` | `src_system` | Source system |
| `raw_imaging_reports` | `img_date` | Image acquisition date |
| `raw_imaging_reports` | `RECIST_resp` | RECIST response category |
| `raw_imaging_reports` | `pacs_src` | PACS source system |
| `raw_genomic_variants` | `ngs_date` | NGS test date |
| `raw_genomic_variants` | `ClinVar_class` | ClinVar pathogenicity classification |
| `raw_genomic_variants` | `TMB` | Tumour mutational burden |
| `raw_genomic_variants` | `MSI` | Microsatellite instability status |
| `raw_genomic_variants` | `seq_lab` | Sequencing laboratory |
| `raw_radiotherapy_fractions` | `fx_date` | Fraction delivery date |
| `raw_radiotherapy_fractions` | `presc_dose_Gy` | Prescribed dose (Gray) |
| `raw_radiotherapy_fractions` | `deliv_dose_Gy` | Delivered dose (Gray) |
| `raw_radiotherapy_fractions` | `attend_status` | Attendance status |
| `raw_systemic_therapy_orders` | `ord_date` | Order date |
| `raw_systemic_therapy_orders` | `plan_dose_mg` | Planned dose (mg) |
| `raw_systemic_therapy_orders` | `admin_flag` | Administered flag |
| `raw_systemic_therapy_orders` | `px_system` | Prescribing system |
| `raw_mdt_decisions` | `mdt_date` | MDT meeting date |
| `raw_mdt_decisions` | `rec_plan` | Recommended plan |
| `raw_mdt_decisions` | `trial_eligib_flag` | Clinical trial eligibility flag |
| `raw_mdt_decisions` | `Tx_intent` | Intent of treatment |
| `raw_mdt_decisions` | `mdt_src` | MDT source registry |
| `raw_vte_risk_assessments` | `padua_score`, `caprini_score`, `vte_high_risk_flag`, `pharm_px_rx` | VTE risk scores, high risk flag, prophylaxis medication |
| `raw_vte_events` | `vte_type`, `anatom_site`, `ha_vte_flag`, `icd10_vte` | VTE phenotype, site, hospital-associated flag, ICD-10 code |
| `raw_vte_prophylaxis_admin` | `px_type`, `px_drug`, `dose_mg`, `missed_dose_flag`, `contraind_flag` | Prophylaxis type/drug, dose, missed dose and contraindication flags |
| `raw_falls_risk_screenings` | `morse_score`, `mobility_lvl`, `prior_fall_6m_flag`, `falls_high_risk_flag` | Falls risk score, mobility level, prior falls, high-risk flag |
| `raw_falls_incidents` | `fall_loc`, `unwitnessed_flag`, `head_strike_flag`, `injury_severity` | Fall location, witnessed status, head impact, injury severity |
| `raw_falls_post_event_reviews` | `repeat_fall_7d_flag`, `action_plan`, `reviewer_role` | 7-day recurrence, mitigation plan, reviewer role |
| `raw_inpatient_observations_XXXX` | `obs_dt`, `HR`, `SBP`, `RR`, `temp_C`, `NEWS2`, `ward_loc` | Observation datetime, heart rate, systolic BP, respiratory rate, temperature, NEWS2 score, ward location |
| `raw_cancer_registry_XXXX` | `extract_dt`, `cwt_62d_flag`, `mdt_disc_flag`, `trial_elig_flag`, `travel_dist_km`, `IMD_decile`, `dq_status` | Extract date, cancer wait 62-day flag, MDT discussion flag, trial eligibility, travel distance, deprivation decile, data quality status |

### How to generate

From repository root:

```bash
python -m src simulate --tables 50 --rows 200 --seed 42
```

Defaults:

- Database path: `data/dwh/raw_demo.db`
- Deterministic generation with `--seed`
- If `--tables` exceeds core table count, additional supplemental raw tables are created

### Core table groups

#### Patient and longitudinal cancer data

- `raw_cancer_patients`
- `raw_cancer_diagnoses`
- `raw_cancer_treatments`
- `raw_cancer_outcomes`
- `raw_lab_results`

#### Inpatient data

- `raw_inpatient_spells`
- `raw_inpatient_episodes`
- `raw_inpatient_observations_XXXX` (generated as scale-up tables)

#### VTE model data

- `raw_vte_risk_assessments`
- `raw_vte_events`
- `raw_vte_prophylaxis_admin`

#### Falls model data

- `raw_falls_risk_screenings`
- `raw_falls_incidents`
- `raw_falls_post_event_reviews`

#### Diverse cancer resources (overlapping)

- `raw_pathology_reports`
- `raw_imaging_reports`
- `raw_genomic_variants`
- `raw_radiotherapy_fractions`
- `raw_systemic_therapy_orders`
- `raw_mdt_decisions`
- `raw_cancer_registry_XXXX` (generated as scale-up tables)

### Scale defaults

With the default settings (`--tables 50 --rows 200 --seed 42`), the source database contains:

- 50 raw tables in total
- 200 patients in `raw_cancer_patients`
- 240 diagnosis rows
- 360 inpatient spells
- 700 lab result rows
- 396 VTE assessment rows, 70 VTE event rows, and 503 VTE prophylaxis rows
- 468 falls screening rows, 56 falls incident rows, and 52 falls post-event review rows
- alternating observation and registry scale-up tables until the requested table count is reached

### Overlap model

Overlap is deliberate and useful for feasibility testing:

- `patient_sk` links patient-level records across most tables
- `case_ref` links multi-source oncology resources such as pathology, imaging, genomics, MDT, and therapy orders
- A single patient can have many spells, episodes, lab results, treatments, and source records

This allows realistic tests for:

- Cross-table joins
- Entity matching
- Feature availability across sources
- Duplicate/discordant evidence handling

### Anonymisation and safety

This is synthetic data and does not contain real patient identifiers.

- `patient_sk` and `pseudo_nhs_id` are generated tokens
- Clinical-like fields are simulated from probabilistic distributions
- Dates and codes are plausible but synthetic

### Quick inspection queries

```sql
-- Count all raw tables
SELECT COUNT(*)
FROM sqlite_master
WHERE type='table' AND name LIKE 'raw_%';

-- List table names
SELECT name
FROM sqlite_master
WHERE type='table' AND name LIKE 'raw_%'
ORDER BY name;

-- Row counts for major tables
SELECT 'raw_cancer_patients' AS table_name, COUNT(*) AS c FROM raw_cancer_patients
UNION ALL
SELECT 'raw_cancer_diagnoses', COUNT(*) FROM raw_cancer_diagnoses
UNION ALL
SELECT 'raw_inpatient_spells', COUNT(*) FROM raw_inpatient_spells
UNION ALL
SELECT 'raw_inpatient_episodes', COUNT(*) FROM raw_inpatient_episodes
UNION ALL
SELECT 'raw_cancer_treatments', COUNT(*) FROM raw_cancer_treatments
UNION ALL
SELECT 'raw_lab_results', COUNT(*) FROM raw_lab_results
UNION ALL
SELECT 'raw_cancer_outcomes', COUNT(*) FROM raw_cancer_outcomes;

-- Example overlap across pathology, imaging, and genomics
SELECT p.case_ref, p.patient_sk, p.specimen_type, p.histo_result,
       i.img_date, i.modality, i.RECIST_resp,
       g.gene_symbol, g.ClinVar_class, g.TMB
FROM raw_pathology_reports p
JOIN raw_imaging_reports i USING (case_ref)
JOIN raw_genomic_variants g USING (case_ref)
LIMIT 20;

-- Example patient timeline: diagnosis → treatment → outcome
SELECT pt.patient_sk, pt.YOB, pt.sex,
       dx.dx_date, dx.TumourSite, dx.ICD10_code, dx.Clinical_Stage,
       tx.Tx_start_date, tx.Tx_modality, tx.Tx_response,
       oc.OS_days, oc.PFS_days, oc.EA_90d_flag
FROM raw_cancer_patients pt
JOIN raw_cancer_diagnoses dx USING (patient_sk)
LEFT JOIN raw_cancer_treatments tx USING (patient_sk)
LEFT JOIN raw_cancer_outcomes oc USING (patient_sk)
LIMIT 20;

-- Example inpatient spell summary
SELECT sp.patient_sk, sp.adm_date, sp.dis_date, sp.LOS_days, sp.Adm_Method,
       ep.cons_code, ep.proc_OPCS4, ep.Dx_ICD10, ep.cost_GBP
FROM raw_inpatient_spells sp
JOIN raw_inpatient_episodes ep USING (spell_sk)
ORDER BY sp.adm_date DESC
LIMIT 20;
```

### Recommended demo storyline

1. Generate db with chosen scale (`--tables`, `--rows`).
2. Show multi-source overlap using `case_ref` joins.
3. Run profiling/scoring pipeline.
4. Present ranked feasible data points and readiness report.
