-- Step 8 (optional): create a mock Snowflake database for feasibility testing.
-- Output:
--   - 1 database
--   - 5 schemas
--   - 20 tables per schema (pathology, cancer, secondary care coverage)
--   - each table has 10 columns and 1000 populated rows

SET mock_database_name = 'MOCK_FEASIBILITY_DB';
SET mock_rows_per_table = 1000;

CREATE DATABASE IF NOT EXISTS IDENTIFIER($mock_database_name);

CREATE SCHEMA IF NOT EXISTS IDENTIFIER($mock_database_name || '.CERNER_RAW');
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($mock_database_name || '.SOMERSYSTEM_RAW');
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($mock_database_name || '.NWL_PATHOLOGY_RAW');
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($mock_database_name || '.INTEGRATED_RAW');
CREATE SCHEMA IF NOT EXISTS IDENTIFIER($mock_database_name || '.REFERENCE_RAW');

CREATE OR REPLACE TEMP TABLE tmp_mock_schemas (
    schema_name STRING,
    source_system STRING
);

INSERT INTO tmp_mock_schemas (schema_name, source_system)
SELECT * FROM VALUES
    ('CERNER_RAW', 'Cerner'),
    ('SOMERSYSTEM_RAW', 'SomerSystem'),
    ('NWL_PATHOLOGY_RAW', 'Northwest London Pathology'),
    ('INTEGRATED_RAW', 'Integrated'),
    ('REFERENCE_RAW', 'Reference');

CREATE OR REPLACE TEMP TABLE tmp_mock_table_templates (
    table_name STRING,
    domain_group STRING,
    topic_label STRING,
    record_prefix STRING
);

INSERT INTO tmp_mock_table_templates (table_name, domain_group, topic_label, record_prefix)
SELECT * FROM VALUES
    ('PATHOLOGY_SPECIMENS', 'Pathology', 'Specimens', 'PSP'),
    ('PATHOLOGY_BIOPSY_REPORTS', 'Pathology', 'Biopsy Reports', 'PBR'),
    ('PATHOLOGY_HISTOLOGY_RESULTS', 'Pathology', 'Histology', 'PHR'),
    ('PATHOLOGY_CYTOLOGY_RESULTS', 'Pathology', 'Cytology', 'PCR'),
    ('PATHOLOGY_MOLECULAR_RESULTS', 'Pathology', 'Molecular', 'PMR'),
    ('PATHOLOGY_LAB_ORDERS', 'Pathology', 'Lab Orders', 'PLO'),
    ('PATHOLOGY_TURNAROUND', 'Pathology', 'Turnaround', 'PTR'),
    ('CANCER_DIAGNOSES', 'Cancer', 'Diagnoses', 'CDX'),
    ('CANCER_STAGING', 'Cancer', 'Staging', 'CST'),
    ('CANCER_TREATMENTS', 'Cancer', 'Treatments', 'CTR'),
    ('CANCER_OUTCOMES', 'Cancer', 'Outcomes', 'COT'),
    ('CANCER_REGISTRY_LINKS', 'Cancer', 'Registry', 'CRL'),
    ('CANCER_MDT_DECISIONS', 'Cancer', 'MDT', 'CMD'),
    ('CANCER_SURVIVAL', 'Cancer', 'Survival', 'CSV'),
    ('SECONDARY_CARE_ADMISSIONS', 'SecondaryCare', 'Admissions', 'SCA'),
    ('SECONDARY_CARE_EPISODES', 'SecondaryCare', 'Episodes', 'SCE'),
    ('SECONDARY_CARE_DISCHARGES', 'SecondaryCare', 'Discharges', 'SCD'),
    ('SECONDARY_CARE_PROCEDURES', 'SecondaryCare', 'Procedures', 'SCP'),
    ('SECONDARY_CARE_OBSERVATIONS', 'SecondaryCare', 'Observations', 'SCO'),
    ('SECONDARY_CARE_REFERRALS', 'SecondaryCare', 'Referrals', 'SCR');

BEGIN
    LET v_create_sql STRING;
    LET v_insert_sql STRING;

    FOR schema_rec IN (SELECT schema_name, source_system FROM tmp_mock_schemas)
    DO
        FOR table_rec IN (
            SELECT table_name, domain_group, topic_label, record_prefix
            FROM tmp_mock_table_templates
            ORDER BY table_name
        )
        DO
            v_create_sql :=
                'CREATE OR REPLACE TABLE "' || REPLACE($mock_database_name, '"', '""') || '"."' || REPLACE(schema_rec.schema_name, '"', '""') || '"."' || REPLACE(table_rec.table_name, '"', '""') || '" (' ||
                'row_id NUMBER, ' ||
                'patient_sk STRING, ' ||
                'record_id STRING, ' ||
                'domain_group STRING, ' ||
                'topic_label STRING, ' ||
                'smoking_status STRING, ' ||
                'treatment_response STRING, ' ||
                'overall_survival_days NUMBER, ' ||
                'event_date DATE, ' ||
                'source_system STRING)';

            EXECUTE IMMEDIATE :v_create_sql;

            v_insert_sql :=
                'INSERT INTO "' || REPLACE($mock_database_name, '"', '""') || '"."' || REPLACE(schema_rec.schema_name, '"', '""') || '"."' || REPLACE(table_rec.table_name, '"', '""') || '" ' ||
                'SELECT ' ||
                'seq4() + 1 AS row_id, ' ||
                '''PT_'' || LPAD(TO_VARCHAR(UNIFORM(1, 5000, RANDOM())), 6, ''0'') AS patient_sk, ' ||
                '''' || REPLACE(table_rec.record_prefix, '''', '''''') || '_'' || LPAD(TO_VARCHAR(seq4() + 1), 7, ''0'') AS record_id, ' ||
                '''' || REPLACE(table_rec.domain_group, '''', '''''') || ''' AS domain_group, ' ||
                '''' || REPLACE(table_rec.topic_label, '''', '''''') || ''' AS topic_label, ' ||
                'ARRAY_CONSTRUCT(''Never'', ''Former'', ''Current'')[UNIFORM(0, 3, RANDOM())]::STRING AS smoking_status, ' ||
                'ARRAY_CONSTRUCT(''Complete'', ''Partial'', ''Stable'', ''Progressive'')[UNIFORM(0, 4, RANDOM())]::STRING AS treatment_response, ' ||
                'UNIFORM(30, 2500, RANDOM()) AS overall_survival_days, ' ||
                'DATEADD(day, -UNIFORM(1, 3650, RANDOM()), CURRENT_DATE()) AS event_date, ' ||
                '''' || REPLACE(schema_rec.source_system, '''', '''''') || ''' AS source_system ' ||
                'FROM TABLE(GENERATOR(ROWCOUNT => ' || $mock_rows_per_table || '))';

            EXECUTE IMMEDIATE :v_insert_sql;
        END FOR;
    END FOR;
END;

-- Validation checks
SELECT
    table_schema,
    COUNT(*) AS table_count,
    MIN(row_count) AS min_row_count,
    MAX(row_count) AS max_row_count
FROM IDENTIFIER($mock_database_name || '.INFORMATION_SCHEMA.TABLES')
WHERE table_schema IN ('CERNER_RAW', 'SOMERSYSTEM_RAW', 'NWL_PATHOLOGY_RAW', 'INTEGRATED_RAW', 'REFERENCE_RAW')
GROUP BY table_schema
ORDER BY table_schema;

SELECT
    table_schema,
    table_name,
    COUNT(*) AS column_count
FROM IDENTIFIER($mock_database_name || '.INFORMATION_SCHEMA.COLUMNS')
WHERE table_schema IN ('CERNER_RAW', 'SOMERSYSTEM_RAW', 'NWL_PATHOLOGY_RAW', 'INTEGRATED_RAW', 'REFERENCE_RAW')
GROUP BY table_schema, table_name
ORDER BY table_schema, table_name;
