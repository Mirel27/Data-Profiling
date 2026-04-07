-- Step 7: export helper queries for CSV/Excel-style deliverables.
-- In Snowsight, run each SELECT and download as CSV.

-- 1) Detailed feasibility candidates (best for analyst workbook)
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

-- 2) Executive summary
SELECT
    source_system,
    concept_name,
    matched_columns,
    green_count,
    amber_count,
    red_count,
    avg_feasibility_score,
    max_feasibility_score,
    avg_populated_pct
FROM ANALYTICS_FEASIBILITY.v_feasibility_summary
ORDER BY source_system, concept_name;

-- 3) Risk register (low and medium feasibility)
SELECT
    source_system,
    concept_name,
    catalog_name,
    schema_name,
    table_name,
    column_name,
    populated_pct,
    feasibility_score,
    rag_score,
    recommendation
FROM ANALYTICS_FEASIBILITY.v_dashboard_data_quality_risk
ORDER BY feasibility_score ASC, populated_pct ASC;
