-- Snowflake SQL-only feasibility assessment setup
-- Creates control schema and core tables used by downstream steps.

CREATE SCHEMA IF NOT EXISTS ANALYTICS_FEASIBILITY;

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.requested_concepts (
    concept_name STRING,
    concept_group STRING,
    priority NUMBER(3,0),
    concept_regex STRING,
    expected_data_type STRING,
    notes STRING
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.source_system_patterns (
    source_system STRING,
    match_regex STRING,
    priority NUMBER(3,0)
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.table_inventory (
    catalog_name STRING,
    schema_name STRING,
    table_name STRING,
    table_type STRING,
    row_count NUMBER,
    bytes NUMBER,
    table_comment STRING,
    discovered_at TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.column_inventory (
    catalog_name STRING,
    schema_name STRING,
    table_name STRING,
    column_name STRING,
    ordinal_position NUMBER,
    data_type STRING,
    is_nullable STRING,
    character_maximum_length NUMBER,
    numeric_precision NUMBER,
    numeric_scale NUMBER,
    column_comment STRING,
    discovered_at TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.concept_column_matches (
    concept_name STRING,
    concept_group STRING,
    source_system STRING,
    catalog_name STRING,
    schema_name STRING,
    table_name STRING,
    column_name STRING,
    data_type STRING,
    metadata_match_score NUMBER(8,4),
    match_reason STRING,
    discovered_at TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.column_quality_profile (
    source_system STRING,
    concept_name STRING,
    catalog_name STRING,
    schema_name STRING,
    table_name STRING,
    column_name STRING,
    row_count NUMBER,
    non_null_count NUMBER,
    populated_pct NUMBER(8,4),
    approx_distinct_count NUMBER,
    null_count NUMBER,
    sample_mode STRING,
    profiled_at TIMESTAMP_NTZ
);

CREATE OR REPLACE TABLE ANALYTICS_FEASIBILITY.feasibility_report (
    source_system STRING,
    concept_name STRING,
    concept_group STRING,
    catalog_name STRING,
    schema_name STRING,
    table_name STRING,
    column_name STRING,
    data_type STRING,
    metadata_match_score NUMBER(8,4),
    row_count NUMBER,
    non_null_count NUMBER,
    populated_pct NUMBER(8,4),
    approx_distinct_count NUMBER,
    rag_score STRING,
    feasibility_score NUMBER(8,4),
    recommendation STRING,
    refreshed_at TIMESTAMP_NTZ
);

BEGIN
    IF COALESCE($reset_seed_data, TRUE) THEN
        TRUNCATE TABLE ANALYTICS_FEASIBILITY.source_system_patterns;
        INSERT INTO ANALYTICS_FEASIBILITY.source_system_patterns (source_system, match_regex, priority)
        SELECT * FROM VALUES
            ('Cerner', '(?i)(cerner|millennium|powerchart|encntr|person_id|mrn)', 1),
            ('SomerSystem', '(?i)(somer|somersystem|systmone|emis|primary_care|gp_)', 1),
            ('Northwest London Pathology', '(?i)(patholog|nwlp|northwest[_ ]london|lab[_ ]result|specimen)', 1);

        TRUNCATE TABLE ANALYTICS_FEASIBILITY.requested_concepts;
        INSERT INTO ANALYTICS_FEASIBILITY.requested_concepts
            (concept_name, concept_group, priority, concept_regex, expected_data_type, notes)
        SELECT * FROM VALUES
            ('Smoking Status', 'Risk Factors', 1, '(?i)(smok|tobacco|pack[_ ]?year)', 'VARCHAR', 'Current, former, never'),
            ('Treatment Response', 'Outcomes', 1, '(?i)(response|recist|progression|stable[_ ]?disease)', 'VARCHAR', 'Clinical treatment response markers'),
            ('Overall Survival', 'Outcomes', 1, '(?i)(overall[_ ]?survival|os[_ ]?(month|days)?|survival)', 'NUMBER', 'Duration or event indicator'),
            ('Pathology Result', 'Diagnostics', 2, '(?i)(patholog|histolog|cytolog|specimen|biopsy)', 'VARCHAR', 'Pathology observations'),
            ('Diagnosis Code', 'Clinical Classification', 2, '(?i)(icd|diagnos|snomed|code)', 'VARCHAR', 'ICD or SNOMED concepts'),
            ('Encounter Date', 'Activity', 2, '(?i)(encounter[_ ]?date|visit[_ ]?date|admit|discharge)', 'DATE', 'Activity timeline anchor');
    END IF;
END;
