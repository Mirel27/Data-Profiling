-- Step 3: data quality profiling for matched columns.
-- Uses Snowflake SQL scripting and dynamic SQL (no Python/UDF requirement).

CREATE OR REPLACE PROCEDURE ANALYTICS_FEASIBILITY.sp_profile_matched_columns(
    sample_pct FLOAT,
    min_match_score FLOAT
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    v_sql STRING;
    v_row_count NUMBER;
    v_non_null_count NUMBER;
    v_approx_distinct NUMBER;
    v_sample_clause STRING;
    v_processed NUMBER DEFAULT 0;
BEGIN
    IF sample_pct IS NULL OR sample_pct >= 100 THEN
        v_sample_clause := '';
    ELSE
        v_sample_clause := ' TABLESAMPLE BERNOULLI (' || sample_pct || ') ';
    END IF;

    DELETE FROM ANALYTICS_FEASIBILITY.column_quality_profile;

    FOR rec IN (
        SELECT
            source_system,
            concept_name,
            catalog_name,
            schema_name,
            table_name,
            column_name
        FROM ANALYTICS_FEASIBILITY.concept_column_matches
        WHERE metadata_match_score >= COALESCE(min_match_score, 0.40)
    )
    DO
        v_sql :=
            'SELECT ' ||
            'COUNT(*) AS row_count, ' ||
            'COUNT_IF("' || REPLACE(rec.column_name, '"', '""') || '" IS NOT NULL) AS non_null_count, ' ||
            'APPROX_COUNT_DISTINCT("' || REPLACE(rec.column_name, '"', '""') || '") AS approx_distinct_count ' ||
            'FROM "' || REPLACE(rec.catalog_name, '"', '""') || '"."' || REPLACE(rec.schema_name, '"', '""') || '"."' || REPLACE(rec.table_name, '"', '""') || '"' ||
            v_sample_clause;

        EXECUTE IMMEDIATE :v_sql INTO :v_row_count, :v_non_null_count, :v_approx_distinct;

        INSERT INTO ANALYTICS_FEASIBILITY.column_quality_profile (
            source_system,
            concept_name,
            catalog_name,
            schema_name,
            table_name,
            column_name,
            row_count,
            non_null_count,
            populated_pct,
            approx_distinct_count,
            null_count,
            sample_mode,
            profiled_at
        )
        SELECT
            rec.source_system,
            rec.concept_name,
            rec.catalog_name,
            rec.schema_name,
            rec.table_name,
            rec.column_name,
            v_row_count,
            v_non_null_count,
            IFF(v_row_count = 0, 0, ROUND((v_non_null_count / v_row_count) * 100, 4)),
            v_approx_distinct,
            GREATEST(v_row_count - v_non_null_count, 0),
            IFF(sample_pct IS NULL OR sample_pct >= 100, 'FULL_SCAN', 'TABLESAMPLE_' || sample_pct || '_PCT'),
            CURRENT_TIMESTAMP();

        v_processed := v_processed + 1;
    END FOR;

    RETURN 'Profiled matched columns: ' || v_processed;
END;
$$;

-- Example execution patterns:
-- CALL ANALYTICS_FEASIBILITY.sp_profile_matched_columns(10, 0.40);
-- CALL ANALYTICS_FEASIBILITY.sp_profile_matched_columns(100, 0.50);
