#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${1:-data/dwh/mock_feasibility_sqlite.db}"
ROWS_PER_TABLE="${2:-1000}"

mkdir -p "$(dirname "$DB_PATH")"

# SQLite does not support schemas like Snowflake; schema names are encoded in table prefixes.
declare -a SCHEMAS=(
  "cerner_raw|Cerner"
  "somersystem_raw|SomerSystem"
  "nwl_pathology_raw|Northwest London Pathology"
  "integrated_raw|Integrated"
  "reference_raw|Reference"
)

declare -a TABLES=(
  "pathology_specimens|Pathology|Specimens|PSP"
  "pathology_biopsy_reports|Pathology|Biopsy Reports|PBR"
  "pathology_histology_results|Pathology|Histology|PHR"
  "pathology_cytology_results|Pathology|Cytology|PCR"
  "pathology_molecular_results|Pathology|Molecular|PMR"
  "pathology_lab_orders|Pathology|Lab Orders|PLO"
  "pathology_turnaround|Pathology|Turnaround|PTR"
  "cancer_diagnoses|Cancer|Diagnoses|CDX"
  "cancer_staging|Cancer|Staging|CST"
  "cancer_treatments|Cancer|Treatments|CTR"
  "cancer_outcomes|Cancer|Outcomes|COT"
  "cancer_registry_links|Cancer|Registry|CRL"
  "cancer_mdt_decisions|Cancer|MDT|CMD"
  "cancer_survival|Cancer|Survival|CSV"
  "secondary_care_admissions|SecondaryCare|Admissions|SCA"
  "secondary_care_episodes|SecondaryCare|Episodes|SCE"
  "secondary_care_discharges|SecondaryCare|Discharges|SCD"
  "secondary_care_procedures|SecondaryCare|Procedures|SCP"
  "secondary_care_observations|SecondaryCare|Observations|SCO"
  "secondary_care_referrals|SecondaryCare|Referrals|SCR"
)

sqlite3 "$DB_PATH" "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"

for schema_entry in "${SCHEMAS[@]}"; do
  IFS='|' read -r schema_name source_system <<< "$schema_entry"

  for table_entry in "${TABLES[@]}"; do
    IFS='|' read -r table_name domain_group topic_label record_prefix <<< "$table_entry"
    full_table_name="${schema_name}__${table_name}"

    sqlite3 "$DB_PATH" <<SQL
DROP TABLE IF EXISTS ${full_table_name};
CREATE TABLE ${full_table_name} (
  row_id INTEGER,
  patient_sk TEXT,
  record_id TEXT,
  domain_group TEXT,
  topic_label TEXT,
  smoking_status TEXT,
  treatment_response TEXT,
  overall_survival_days INTEGER,
  event_date TEXT,
  source_system TEXT
);

WITH RECURSIVE seq(x) AS (
  SELECT 1
  UNION ALL
  SELECT x + 1 FROM seq WHERE x < ${ROWS_PER_TABLE}
)
INSERT INTO ${full_table_name}
SELECT
  x AS row_id,
  'PT_' || printf('%06d', abs(random() % 5000) + 1) AS patient_sk,
  '${record_prefix}_' || printf('%07d', x) AS record_id,
  '${domain_group}' AS domain_group,
  '${topic_label}' AS topic_label,
  CASE abs(random() % 3)
    WHEN 0 THEN 'Never'
    WHEN 1 THEN 'Former'
    ELSE 'Current'
  END AS smoking_status,
  CASE abs(random() % 4)
    WHEN 0 THEN 'Complete'
    WHEN 1 THEN 'Partial'
    WHEN 2 THEN 'Stable'
    ELSE 'Progressive'
  END AS treatment_response,
  abs(random() % 2471) + 30 AS overall_survival_days,
  date('now', '-' || (abs(random() % 3650) + 1) || ' day') AS event_date,
  '${source_system}' AS source_system
FROM seq;
SQL
  done
done

echo "Created SQLite mock feasibility database at: ${DB_PATH}"
echo "Expected table count: 100"
echo "Expected rows per table: ${ROWS_PER_TABLE}"
