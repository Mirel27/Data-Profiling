-- Step 5: Snowsight dashboard views.
-- Build dashboard tiles directly from these views.

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_dashboard_kpis AS
SELECT
    COUNT(*) AS total_matches,
    COUNT_IF(rag_score = 'GREEN') AS green_matches,
    COUNT_IF(rag_score = 'AMBER') AS amber_matches,
    COUNT_IF(rag_score = 'RED') AS red_matches,
    ROUND(AVG(feasibility_score), 4) AS overall_avg_feasibility,
    ROUND(AVG(populated_pct), 4) AS overall_avg_population,
    MAX(refreshed_at) AS latest_refresh_ts
FROM ANALYTICS_FEASIBILITY.feasibility_report;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_dashboard_source_rag AS
SELECT
    source_system,
    rag_score,
    COUNT(*) AS match_count,
    ROUND(AVG(feasibility_score), 4) AS avg_feasibility_score
FROM ANALYTICS_FEASIBILITY.feasibility_report
GROUP BY source_system, rag_score
ORDER BY source_system,
         CASE rag_score WHEN 'GREEN' THEN 1 WHEN 'AMBER' THEN 2 ELSE 3 END;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_dashboard_concept_heatmap AS
SELECT
    source_system,
    concept_name,
    COUNT(*) AS matched_columns,
    ROUND(AVG(feasibility_score), 4) AS avg_feasibility_score,
    ROUND(MAX(feasibility_score), 4) AS best_feasibility_score,
    COUNT_IF(rag_score = 'GREEN') AS green_columns,
    COUNT_IF(rag_score = 'AMBER') AS amber_columns,
    COUNT_IF(rag_score = 'RED') AS red_columns
FROM ANALYTICS_FEASIBILITY.feasibility_report
GROUP BY source_system, concept_name
ORDER BY source_system, concept_name;

CREATE OR REPLACE VIEW ANALYTICS_FEASIBILITY.v_dashboard_data_quality_risk AS
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
FROM ANALYTICS_FEASIBILITY.feasibility_report
WHERE rag_score IN ('RED', 'AMBER')
ORDER BY feasibility_score ASC, populated_pct ASC;
