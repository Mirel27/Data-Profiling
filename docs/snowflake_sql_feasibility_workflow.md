# Snowflake SQL-Only Feasibility Workflow

This workflow supports large-scale feasibility assessment across 1000+ raw tables using only Snowflake SQL.

Covered scope:
- Field discovery
- Data quality profiling
- Concept-to-source mapping
- Feasibility reporting with RAG scoring
- Snowsight dashboard-ready outputs

Environment assumptions:
- Snowflake warehouse is available
- Full INFORMATION_SCHEMA access on target database
- Source systems include Cerner, SomerSystem, and Northwest London Pathology

## SQL artifacts

- `sql/snowflake/00_bootstrap.sql`
- `sql/snowflake/01_setup.sql`
- `sql/snowflake/02_metadata_discovery.sql`
- `sql/snowflake/03_quality_profile.sql`
- `sql/snowflake/04_feasibility_scoring.sql`
- `sql/snowflake/05_dashboard_views.sql`
- `sql/snowflake/06_run_all.sql`
- `sql/snowflake/07_exports.sql`
- `sql/snowflake/08_mock_feasibility_database.sql`

## Run order

0. Optional: create mock database for dry-run testing:

```sql
!source sql/snowflake/08_mock_feasibility_database.sql

-- then point discovery to mock database
SET target_database = 'MOCK_FEASIBILITY_DB';
SET target_schema_like = '%';
```

1. Run bootstrap script and set session variables:

```sql
!source sql/snowflake/00_bootstrap.sql
```

2. Run full pipeline in one script:

```sql
!source sql/snowflake/06_run_all.sql
```

3. Optional step-by-step mode (instead of run-all):

```sql
-- Creates ANALYTICS_FEASIBILITY schema and core tables.
!source sql/snowflake/01_setup.sql
```

4. Set metadata scan scope and run discovery:

```sql
SET target_database = 'ICHT_PROD';
SET target_schema_like = '%';

!source sql/snowflake/02_metadata_discovery.sql
```

5. Run quality profiling for matched columns:

```sql
!source sql/snowflake/03_quality_profile.sql

-- Fast scan for scale testing:
CALL ANALYTICS_FEASIBILITY.sp_profile_matched_columns(10, 0.40);

-- Full scan for final reporting:
-- CALL ANALYTICS_FEASIBILITY.sp_profile_matched_columns(100, 0.40);
```

6. Build feasibility report and scoring outputs:

```sql
!source sql/snowflake/04_feasibility_scoring.sql
```

7. Create Snowsight dashboard views:

```sql
!source sql/snowflake/05_dashboard_views.sql
```

8. Run export helper queries:

```sql
!source sql/snowflake/07_exports.sql
```

## RAG scoring logic

Feasibility score is weighted as:

$$
\text{Feasibility} = 0.45 \cdot \text{MetadataMatch} + 0.40 \cdot \text{PopulationCompleteness} + 0.15 \cdot \text{Distinctiveness}
$$

Where:
- MetadataMatch: regex-based concept relevance in column/table names and comments
- PopulationCompleteness: populated percentage scaled to [0, 1]
- Distinctiveness: log-scaled cardinality from `APPROX_COUNT_DISTINCT`

RAG classification:
- GREEN: score >= 0.75
- AMBER: 0.45 <= score < 0.75
- RED: score < 0.45

## Output surfaces

CSV/Excel-style report:
- Query `ANALYTICS_FEASIBILITY.v_feasibility_top_candidates`
- Download results as CSV from Snowsight
- Open CSV in Excel if XLSX delivery is needed

Snowsight dashboard sources:
- `ANALYTICS_FEASIBILITY.v_dashboard_kpis`
- `ANALYTICS_FEASIBILITY.v_dashboard_source_rag`
- `ANALYTICS_FEASIBILITY.v_dashboard_concept_heatmap`
- `ANALYTICS_FEASIBILITY.v_dashboard_data_quality_risk`

## Customization points

- Update concept list in `ANALYTICS_FEASIBILITY.requested_concepts`
- Tune source classification regex in `ANALYTICS_FEASIBILITY.source_system_patterns`
- Adjust profiling cost/accuracy via `sample_pct`
- Tune relevance cutoff with `min_match_score`

Optional custom seed flow:
- Insert custom rows into `tmp_requested_concepts` and `tmp_source_system_patterns` after running `00_bootstrap.sql`
- Set `use_custom_seed_temp_tables = TRUE`
- Run `06_run_all.sql`
