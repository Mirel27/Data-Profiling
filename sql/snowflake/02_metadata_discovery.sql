-- Step 2: metadata discovery for tables/columns and concept-to-source matching.
-- Required session variables before running:
--   SET target_database = 'ICHT_PROD';
--   SET target_schema_like = '%';

DELETE FROM ANALYTICS_FEASIBILITY.table_inventory;
INSERT INTO ANALYTICS_FEASIBILITY.table_inventory
SELECT
    table_catalog AS catalog_name,
    table_schema AS schema_name,
    table_name,
    table_type,
    row_count,
    bytes,
    comment AS table_comment,
    CURRENT_TIMESTAMP() AS discovered_at
FROM IDENTIFIER($target_database || '.INFORMATION_SCHEMA.TABLES')
WHERE table_schema ILIKE $target_schema_like
  AND table_type IN ('BASE TABLE', 'EXTERNAL TABLE');

DELETE FROM ANALYTICS_FEASIBILITY.column_inventory;
INSERT INTO ANALYTICS_FEASIBILITY.column_inventory
SELECT
    table_catalog AS catalog_name,
    table_schema AS schema_name,
    table_name,
    column_name,
    ordinal_position,
    data_type,
    is_nullable,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    comment AS column_comment,
    CURRENT_TIMESTAMP() AS discovered_at
FROM IDENTIFIER($target_database || '.INFORMATION_SCHEMA.COLUMNS')
WHERE table_schema ILIKE $target_schema_like;

DELETE FROM ANALYTICS_FEASIBILITY.concept_column_matches;

INSERT INTO ANALYTICS_FEASIBILITY.concept_column_matches
WITH joined_inventory AS (
    SELECT
        c.catalog_name,
        c.schema_name,
        c.table_name,
        c.column_name,
        c.data_type,
        COALESCE(t.table_comment, '') AS table_comment,
        COALESCE(c.column_comment, '') AS column_comment,
        COALESCE(t.row_count, 0) AS table_row_count
    FROM ANALYTICS_FEASIBILITY.column_inventory c
    INNER JOIN ANALYTICS_FEASIBILITY.table_inventory t
        ON c.catalog_name = t.catalog_name
       AND c.schema_name = t.schema_name
       AND c.table_name = t.table_name
),
matched AS (
    SELECT
        rc.concept_name,
        rc.concept_group,
        COALESCE(
            (
                SELECT sp.source_system
                FROM ANALYTICS_FEASIBILITY.source_system_patterns sp
                WHERE REGEXP_LIKE(
                    CONCAT_WS(' ', ji.catalog_name, ji.schema_name, ji.table_name, ji.column_name, ji.table_comment, ji.column_comment),
                    sp.match_regex
                )
                ORDER BY sp.priority ASC
                LIMIT 1
            ),
            'Unknown'
        ) AS source_system,
        ji.catalog_name,
        ji.schema_name,
        ji.table_name,
        ji.column_name,
        ji.data_type,
        (
            IFF(REGEXP_LIKE(ji.column_name, rc.concept_regex), 0.65, 0) +
            IFF(REGEXP_LIKE(ji.column_comment, rc.concept_regex), 0.20, 0) +
            IFF(REGEXP_LIKE(ji.table_name, rc.concept_regex), 0.10, 0) +
            IFF(REGEXP_LIKE(ji.table_comment, rc.concept_regex), 0.05, 0)
        ) AS metadata_match_score,
        CONCAT(
            IFF(REGEXP_LIKE(ji.column_name, rc.concept_regex), 'column_name;', ''),
            IFF(REGEXP_LIKE(ji.column_comment, rc.concept_regex), 'column_comment;', ''),
            IFF(REGEXP_LIKE(ji.table_name, rc.concept_regex), 'table_name;', ''),
            IFF(REGEXP_LIKE(ji.table_comment, rc.concept_regex), 'table_comment;', '')
        ) AS match_reason
    FROM joined_inventory ji
    CROSS JOIN ANALYTICS_FEASIBILITY.requested_concepts rc
)
SELECT
    concept_name,
    concept_group,
    source_system,
    catalog_name,
    schema_name,
    table_name,
    column_name,
    data_type,
    metadata_match_score,
    NULLIF(match_reason, '') AS match_reason,
    CURRENT_TIMESTAMP() AS discovered_at
FROM matched
WHERE metadata_match_score >= 0.20;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_concept_match_summary AS
SELECT
    source_system,
    concept_name,
    COUNT(*) AS matched_columns,
    COUNT(DISTINCT CONCAT_WS('.', catalog_name, schema_name, table_name)) AS matched_tables,
    ROUND(AVG(metadata_match_score), 4) AS avg_metadata_match_score,
    ROUND(MAX(metadata_match_score), 4) AS max_metadata_match_score
FROM ANALYTICS_FEASIBILITY.concept_column_matches
GROUP BY source_system, concept_name
ORDER BY source_system, concept_name;
