-- Step 0: session bootstrap and runtime parameters.
-- Run this first in Snowsight worksheet.

-- Required runtime context
-- USE ROLE <role_with_required_privileges>;
-- USE WAREHOUSE <warehouse_name>;
-- USE DATABASE <target_database>;
-- USE SCHEMA ANALYTICS_FEASIBILITY;

-- Core parameters
SET target_database = 'ICHT_PROD';
SET target_schema_like = '%';

-- Profiling parameters
SET profile_sample_pct = 10;
SET min_match_score = 0.40;

-- Optional: refresh seeded defaults in setup
SET reset_seed_data = TRUE;

-- Optional: use custom concept and source pattern temp tables.
-- If TRUE, 06_run_all.sql will merge from temp tables into control tables.
SET use_custom_seed_temp_tables = FALSE;

-- Create temp table templates for optional custom seed data.
CREATE OR REPLACE TEMP TABLE tmp_requested_concepts (
    concept_name STRING,
    concept_group STRING,
    priority NUMBER(3,0),
    concept_regex STRING,
    expected_data_type STRING,
    notes STRING
);

CREATE OR REPLACE TEMP TABLE tmp_source_system_patterns (
    source_system STRING,
    match_regex STRING,
    priority NUMBER(3,0)
);

-- Example custom concept rows (commented out)
-- INSERT INTO tmp_requested_concepts VALUES
-- ('ECOG Performance Status', 'Risk Stratification', 1, '(?i)(ecog|performance[_ ]?status)', 'NUMBER', 'Oncology performance index');

-- Example custom source pattern rows (commented out)
-- INSERT INTO tmp_source_system_patterns VALUES
-- ('Cerner', '(?i)(cerner|millennium|powerchart|encntr)', 1);
