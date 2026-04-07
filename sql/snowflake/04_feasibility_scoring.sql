-- Step 4: build RAG feasibility scoring and consolidated report output.

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_feasibility_scoring_base AS
SELECT
    m.source_system,
    m.concept_name,
    m.concept_group,
    m.catalog_name,
    m.schema_name,
    m.table_name,
    m.column_name,
    m.data_type,
    m.metadata_match_score,
    q.row_count,
    q.non_null_count,
    q.populated_pct,
    q.approx_distinct_count,
    COALESCE(
        (0.45 * m.metadata_match_score) +
        (0.40 * LEAST(q.populated_pct / 100, 1)) +
        (0.15 * LEAST(LN(NULLIF(q.approx_distinct_count, 0) + 1) / 8, 1)),
        0
    ) AS feasibility_score
FROM ANALYTICS_FEASIBILITY.concept_column_matches m
LEFT JOIN ANALYTICS_FEASIBILITY.column_quality_profile q
    ON m.source_system = q.source_system
   AND m.concept_name = q.concept_name
   AND m.catalog_name = q.catalog_name
   AND m.schema_name = q.schema_name
   AND m.table_name = q.table_name
   AND m.column_name = q.column_name;

DELETE FROM ANALYTICS_FEASIBILITY.feasibility_report;

INSERT INTO ANALYTICS_FEASIBILITY.feasibility_report
SELECT
    source_system,
    concept_name,
    concept_group,
    catalog_name,
    schema_name,
    table_name,
    column_name,
    data_type,
    ROUND(metadata_match_score, 4) AS metadata_match_score,
    row_count,
    non_null_count,
    populated_pct,
    approx_distinct_count,
    CASE
        WHEN feasibility_score >= 0.75 THEN 'GREEN'
        WHEN feasibility_score >= 0.45 THEN 'AMBER'
        ELSE 'RED'
    END AS rag_score,
    ROUND(feasibility_score, 4) AS feasibility_score,
    CASE
        WHEN feasibility_score >= 0.75 THEN 'Feasible candidate. Prioritize in downstream extraction.'
        WHEN feasibility_score >= 0.45 THEN 'Potentially feasible. Validate business rules and completeness.'
        ELSE 'Low feasibility. Consider alternative concept or additional source.'
    END AS recommendation,
    CURRENT_TIMESTAMP() AS refreshed_at
FROM ANALYTICS_FEASIBILITY.v_feasibility_scoring_base;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_feasibility_top_candidates AS
SELECT
    source_system,
    concept_name,
    concept_group,
    catalog_name,
    schema_name,
    table_name,
    column_name,
    data_type,
    rag_score,
    feasibility_score,
    metadata_match_score,
    populated_pct,
    approx_distinct_count,
    recommendation,
    refreshed_at
FROM ANALYTICS_FEASIBILITY.feasibility_report
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY source_system, concept_name
    ORDER BY feasibility_score DESC, metadata_match_score DESC
) <= 25;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_feasibility_summary AS
SELECT
    source_system,
    concept_name,
    COUNT(*) AS matched_columns,
    COUNT_IF(rag_score = 'GREEN') AS green_count,
    COUNT_IF(rag_score = 'AMBER') AS amber_count,
    COUNT_IF(rag_score = 'RED') AS red_count,
    ROUND(AVG(feasibility_score), 4) AS avg_feasibility_score,
    ROUND(MAX(feasibility_score), 4) AS max_feasibility_score,
    ROUND(AVG(populated_pct), 4) AS avg_populated_pct
FROM ANALYTICS_FEASIBILITY.feasibility_report
GROUP BY source_system, concept_name
ORDER BY source_system, concept_name;

-- CSV/Excel-style extraction query (use Snowsight download results as CSV).
SELECT
    source_system,
    concept_name,
    concept_group,
    catalog_name,
    schema_name,
    table_name,
    column_name,
    data_type,
    rag_score,
    feasibility_score,
    metadata_match_score,
    row_count,
    non_null_count,
    populated_pct,
    approx_distinct_count,
    recommendation,
    refreshed_at
FROM ANALYTICS_FEASIBILITY.v_feasibility_top_candidates
ORDER BY source_system, concept_name, feasibility_score DESC;
