-- Step 6: one-shot orchestration script.
-- Expected sequence:
--   1) Run 00_bootstrap.sql
--   2) Run this script

!source sql/snowflake/01_setup.sql

BEGIN
    IF COALESCE($use_custom_seed_temp_tables, FALSE) THEN
        DELETE FROM ANALYTICS_FEASIBILITY.requested_concepts;
        INSERT INTO ANALYTICS_FEASIBILITY.requested_concepts
        SELECT * FROM tmp_requested_concepts;

        DELETE FROM ANALYTICS_FEASIBILITY.source_system_patterns;
        INSERT INTO ANALYTICS_FEASIBILITY.source_system_patterns
        SELECT * FROM tmp_source_system_patterns;
    END IF;
END;

!source sql/snowflake/02_metadata_discovery.sql
!source sql/snowflake/03_quality_profile.sql

CALL ANALYTICS_FEASIBILITY.sp_profile_matched_columns($profile_sample_pct, $min_match_score);

!source sql/snowflake/04_feasibility_scoring.sql
!source sql/snowflake/05_dashboard_views.sql

-- Quick status checks
SELECT *
FROM ANALYTICS_FEASIBILITY.v_dashboard_kpis;

SELECT *
FROM ANALYTICS_FEASIBILITY.v_feasibility_summary
ORDER BY source_system, concept_name;
