# Fresh Clone Setup

This guide is for a brand new local clone of `data_champs`.

## What this project uses

- Python 3.12
- a local virtual environment in `.venv`
- PySpark for profiling, search, and the Streamlit app data access
- pandas for UI shaping, CSV export, and small in-memory table handling
- Streamlit for the researcher UI
- SQLite for the synthetic source database
- Java 17 for PySpark

## Quick start

### macOS / Linux

From the repo root:

```bash
make setup
make ui
```

`make setup` will:
- create or reuse `.venv`
- install Python dependencies from `requirements.txt`
- install Java 17 locally into `.tools/` if needed
- download the SQLite JDBC jar into the PySpark environment
- generate `data/dwh/raw_demo.db`

Then `make ui` starts the Streamlit app.

### Windows PowerShell

From the repo root:

```powershell
.\scripts\install_windows.ps1
```

That script will:
- create or reuse `.venv`
- install Python dependencies into `.venv`
- generate `data/dwh/raw_demo.db`

To start the UI on Windows:

```powershell
.\.venv\Scripts\python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
```

Note:
- PySpark also needs Java 17 on Windows.
- The PowerShell installer currently does not install Java for you.
- If the UI fails with a Java gateway error, install Java 17 and make sure `JAVA_HOME` points to it.

## Step by step manual setup

Use this only if you do not want the one-command setup.

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
make install-java
make install-jdbc
.venv/bin/python -m src simulate
```

Start the UI:

```bash
.venv/bin/python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m src simulate
```

Start the UI:

```powershell
.\.venv\Scripts\python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
```

## Common commands

From the repo root:

```bash
make setup
make ui
make simulate
make inspect-db
make check-readme-schema
make test
```

Manual equivalents:

```bash
.venv/bin/python -m src simulate
.venv/bin/python scripts/inspect_raw_demo_db.py
.venv/bin/python scripts/check_raw_demo_readme_schema.py
.venv/bin/python -m unittest tests.test_generate_raw_demo_db tests.test_raw_demo_readme_schema
```

## What gets created

Important local/generated paths:

- `.venv/` — local Python environment
- `.tools/` — local Java 17 install on macOS/Linux when needed
- `data/dwh/raw_demo.db` — generated synthetic source database
- `data/processed/` — generated outputs such as reports and profiles

## FAQ

### Do I need to create `.venv` manually?

No. `make setup` on macOS/Linux and `.\scripts\install_windows.ps1` on Windows both create or reuse `.venv`.

### Do I need to install Streamlit globally?

No. Use the project environment:

- macOS/Linux: `.venv/bin/python -m streamlit ...`
- Windows: `.\.venv\Scripts\python -m streamlit ...`

Or just use `make ui` on macOS/Linux.

### Why does the app use both pandas and PySpark?

- pandas is used for UI-facing shaping, filtering, CSV export, and reading small SQLite result sets
- PySpark is used for larger profiling/search workflows and JDBC-based table access

So this repo is not "pandas only" or "Spark only"; it uses both for different jobs.

### What is `raw_demo.db`?

It is the synthetic source SQLite database used by the project.

Default location:

```text
data/dwh/raw_demo.db
```

Regenerate it with:

```bash
make simulate
```

### Why do I get `JAVA_GATEWAY_EXITED`?

That usually means PySpark cannot find a working Java runtime.

Try:

```bash
make setup
make ui
```

If you are launching manually, use the project interpreter:

```bash
.venv/bin/python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
```

On Windows, install Java 17 separately and set `JAVA_HOME`.

### Why do I get `No module named streamlit`?

The app is being run outside the project environment.

Use:

```bash
make ui
```

or:

```bash
.venv/bin/python -m streamlit run apps/streamlit/researcher_ui.py -- --config scripts/config/rbac_tables.example.json
```

### Where is the Streamlit app?

```text
apps/streamlit/researcher_ui.py
```

### Where is the raw database generator?

```text
src/generate_raw_demo_db.py
```

The package entrypoint is:

```bash
.venv/bin/python -m src simulate
```

### How do I know the generated DB matches the documented schema?

Run:

```bash
make check-readme-schema
make test
```

## Recommended workflow

For day-to-day local work:

1. Pull the latest repo changes.
2. Run `make setup`.
3. Run `make ui` if you need the Streamlit app.
4. Run `make test` after changing generator/schema-related code.
