# data_champs
Imperial College Healthcare NHS Trust

Fresh clone setup:
- see [SETUP.md](/Users/macbookpro/Documents/_dev2/data_champs/docs/SETUP.md)

## Setup

This project uses Python dependencies listed in `requirements.txt`.

### Windows (PowerShell, recommended)

Run:

```powershell
.\scripts\install_windows.ps1
```

### Using `make` (recommended for macOS/Linux)

Run:

```bash
make setup
```

This creates or reuses `.venv`, installs Python dependencies, installs Java 17 if needed, downloads the SQLite JDBC jar, and generates the demo source database.

## Generate the raw source database

```bash
python -m src simulate
```

## Inspect the raw source database

```bash
python scripts/inspect_raw_demo_db.py
```

## Check documented schema against the database

```bash
python scripts/check_raw_demo_readme_schema.py
```

## Streamlit app

```bash
make ui
```

## PySpark RBAC Excel Report

Generate an Excel report with:
- Table name
- Row count
- Population percentage for a chosen value column
- Access status based on RBAC
- Top 5 values when allowed
- Permission request guidance when not allowed

### Files
- `scripts/rbac_excel_report.py`
- `scripts/config/rbac_tables.example.json`

### Install

```bash
pip install pyspark openpyxl
```

### Run

```bash
python scripts/rbac_excel_report.py \
	--config scripts/config/rbac_tables.example.json \
	--role analyst \
	--output data/processed/rbac_table_report.xlsx
```

### Notes
- The script uses PySpark DataFrames (lazy execution).
- It uses generators and write-only Excel output to keep memory usage low.
- If `anon_access_all_models` is enabled in config, users without full access can still see anonymized top values.

## Governance Query Guidelines

The following identifier columns are restricted by policy and must not be requested in reports or prompts:
- `subject`
- `encntr_id`
- `episode_id`

If requested, the system should block the request and suggest using non-identifying aggregated fields.

Only one database is allowed for search operations:
- `icht_prod`

If a table config points to any other database, the system marks it as policy blocked.

## Data Profiler

Column-level data quality profiling with RBAC-aware sample suppression and color-coded quality flags.

### Role behavior

| Role | Table/column names | Population stats | Quality flag | Sample values |
|---|---|---|---|---|
| `data_engineer` | Yes | Yes | Yes | Yes (top 5 distinct) |
| `researcher` | Yes | Yes | Yes | **Suppressed** |
| `admin` | Yes | Yes | Yes | Yes |

### Quality color codes

- **GREEN** — populated >= 90%
- **AMBER** — populated >= 50%
- **RED** — populated < 50%

### Run profile

```bash
# Data engineer sees full profile with samples
python scripts/data_profiler.py profile \
  --config scripts/config/rbac_tables.example.json \
  --role data_engineer \
  --output data/processed/data_profile.csv

# Researcher sees table/column/population but no sample values
python scripts/data_profiler.py profile \
  --config scripts/config/rbac_tables.example.json \
  --role researcher \
  --output data/processed/data_profile_researcher.csv
```

### Natural language search

Describe in plain English what data you need. Results are scoped to models you have access to.

```bash
python scripts/data_profiler.py search \
  --config scripts/config/rbac_tables.example.json \
  --role data_engineer \
  --query "smoking history and treatment outcomes" \
  --output data/processed/search_results.csv
```
