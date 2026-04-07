SYSTEM_PYTHON ?= python3
PYTHON     ?= .venv/bin/python
SPARK_JARS = $(shell $(PYTHON) -c "import pyspark, os; print(os.path.join(os.path.dirname(pyspark.__file__), 'jars'))" 2>/dev/null)
JDBC_VER   := 3.45.3.0
JDBC_JAR   := sqlite-jdbc-$(JDBC_VER).jar
CONFIG     := scripts/config/rbac_tables.example.json
TOOLS_DIR  := .tools
LOCAL_JAVA_DIR := $(abspath $(TOOLS_DIR)/java/jdk-17)

.PHONY: venv setup install install-java install-jdbc install-all \
	simulate inspect-db check-readme-schema sql-test test materialize profile search assess report ui \
	sqlite-profile mock-db create-trial-table eligibility consented

JAVA_ENV_CMD = if [ -x "$(LOCAL_JAVA_DIR)/Contents/Home/bin/java" ]; then \
		export JAVA_HOME="$(LOCAL_JAVA_DIR)/Contents/Home"; \
		export PATH="$$JAVA_HOME/bin:$$PATH"; \
	elif [ -x "$(LOCAL_JAVA_DIR)/bin/java" ]; then \
		export JAVA_HOME="$(LOCAL_JAVA_DIR)"; \
		export PATH="$$JAVA_HOME/bin:$$PATH"; \
	elif command -v /usr/libexec/java_home >/dev/null 2>&1 && /usr/libexec/java_home -v 17 >/dev/null 2>&1; then \
		export JAVA_HOME="$$(/usr/libexec/java_home -v 17)"; \
		export PATH="$$JAVA_HOME/bin:$$PATH"; \
	elif [ -f /usr/local/sdkman/bin/sdkman-init.sh ]; then \
		source /usr/local/sdkman/bin/sdkman-init.sh; \
		sdk use java 17.0.12-tem >/dev/null; \
	elif [ -f "$$HOME/.sdkman/bin/sdkman-init.sh" ]; then \
		source "$$HOME/.sdkman/bin/sdkman-init.sh"; \
		sdk use java 17.0.12-tem >/dev/null; \
	else \
		echo "ERROR: Java 17 not found. Run make install-java first."; \
		exit 1; \
	fi

# ── Installation ─────────────────────────────────────────────

venv:                          ## Create the local virtualenv if missing
	@if [ ! -x "$(PYTHON)" ]; then \
		$(SYSTEM_PYTHON) -m venv .venv; \
	fi

setup: install-all simulate      ## One-command bootstrap for fresh clones

install: venv                  ## Install Python dependencies
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt

install-java:                  ## Install Java 17 locally if needed (needed by PySpark)
	@bash -lc 'set -euo pipefail; \
		if [ -x "$(LOCAL_JAVA_DIR)/Contents/Home/bin/java" ] || [ -x "$(LOCAL_JAVA_DIR)/bin/java" ]; then \
			echo "Java 17 already installed at $(LOCAL_JAVA_DIR)"; \
			exit 0; \
		fi; \
		if command -v /usr/libexec/java_home >/dev/null 2>&1 && /usr/libexec/java_home -v 17 >/dev/null 2>&1; then \
			echo "Java 17 already available on this system"; \
			exit 0; \
		fi; \
		os=$$(uname -s); \
		arch=$$(uname -m); \
		case "$$os/$$arch" in \
			Darwin/arm64) platform=mac; jarch=aarch64 ;; \
			Darwin/x86_64) platform=mac; jarch=x64 ;; \
			Linux/x86_64) platform=linux; jarch=x64 ;; \
			Linux/aarch64|Linux/arm64) platform=linux; jarch=aarch64 ;; \
			*) echo "ERROR: Unsupported platform $$os/$$arch for automatic Java install."; exit 1 ;; \
		esac; \
		mkdir -p "$(TOOLS_DIR)/java"; \
		tmpdir=$$(mktemp -d); \
		archive="$$tmpdir/jdk17.tar.gz"; \
		url="https://api.adoptium.net/v3/binary/latest/17/ga/$$platform/$$jarch/jdk/hotspot/normal/eclipse"; \
		echo "Downloading Java 17 from $$url"; \
		curl -fL "$$url" -o "$$archive"; \
		rm -rf "$(LOCAL_JAVA_DIR)"; \
		tar -xzf "$$archive" -C "$$tmpdir"; \
		extracted=$$(find "$$tmpdir" -mindepth 1 -maxdepth 1 -type d | head -n 1); \
		mv "$$extracted" "$(LOCAL_JAVA_DIR)"; \
		rm -rf "$$tmpdir"; \
		echo "Installed Java 17 to $(LOCAL_JAVA_DIR)"'

install-jdbc: install           ## Download SQLite JDBC driver into PySpark jars
	@if [ -z "$(SPARK_JARS)" ]; then \
		echo "ERROR: pyspark not installed – run 'make install' first"; exit 1; \
	fi
	@if [ ! -f "$(SPARK_JARS)/$(JDBC_JAR)" ]; then \
		curl -fSL -o "$(SPARK_JARS)/$(JDBC_JAR)" \
		  "https://repo1.maven.org/maven2/org/xerial/sqlite-jdbc/$(JDBC_VER)/$(JDBC_JAR)"; \
		echo "Downloaded $(JDBC_JAR) → $(SPARK_JARS)/"; \
	else \
		echo "$(JDBC_JAR) already present"; \
	fi

install-all: install install-java install-jdbc  ## Full setup (Python + Java + JDBC)

# ── Run targets ──────────────────────────────────────────────

simulate:                      ## Generate the raw source SQLite database
	$(PYTHON) -m src simulate

inspect-db:                    ## Inspect the generated raw source database
	$(PYTHON) scripts/inspect_raw_demo_db.py

check-readme-schema:           ## Check README-documented schema against raw_demo.db
	$(PYTHON) scripts/check_raw_demo_readme_schema.py

sql-test: inspect-db           ## Backward-compatible alias for DB inspection

test:                          ## Run automated schema and generation tests
	$(PYTHON) -m unittest tests.test_generate_raw_demo_db tests.test_raw_demo_readme_schema

materialize:                   ## Compute full profile and store in SQLite (run once / on data change)
	@bash -c '$(JAVA_ENV_CMD) && \
		$(PYTHON) scripts/data_profiler.py materialize \
		  --config $(CONFIG) \
		  --db data/dwh/raw_demo.db'

profile:                       ## Generate data profile CSV
	@bash -c '$(JAVA_ENV_CMD) && \
		$(PYTHON) scripts/data_profiler.py profile \
		  --config $(CONFIG) \
		  --role researcher \
		  --output data/processed/data_profile.csv'

search:                        ## NL column search  (QUERY="cancer stage")
	@bash -c '$(JAVA_ENV_CMD) && \
		$(PYTHON) scripts/data_profiler.py search \
		  --config $(CONFIG) \
		  --role researcher \
		  --query "$(QUERY)"'

report:                        ## Generate RBAC table report
	@bash -c '$(JAVA_ENV_CMD) && \
		$(PYTHON) scripts/rbac_excel_report.py \
		  --config $(CONFIG) \
		  --role researcher \
		  --output data/processed/rbac_table_report.csv'

sqlite-profile:                ## Run SQLite column-value profiling into column_value_profile table
	$(PYTHON) scripts/run_sqlite_column_profile.py \
	  --db data/dwh/raw_demo.db \
	  --sql-dir sql/sqllite

assess:                        ## Run SQLite feasibility assessment (DATA_POINTS="smoking status, ...")  
	$(PYTHON) scripts/feasibility_assess_sqlite.py \
	  --db data/dwh/mock_feasibility_sqlite.db \
	  --dict data/processed/mock_cancer_data_dictionary_50.csv \
	  --output data/processed/feasibility_assessment.csv

mock-db:                       ## Create mock feasibility SQLite database (runs create_mock_feasibility_sqlite.sh)
	bash scripts/create_mock_feasibility_sqlite.sh

create-trial-table:            ## Build breast cancer phase III clinical trial table in mock_feasibility_sqlite.db
	$(PYTHON) scripts/create_clinical_trial_table.py

eligibility: create-trial-table  ## Generate clinical trial eligibility report for consented patients
	$(PYTHON) scripts/check_trial_eligibility.py

consented: create-trial-table  ## Analyse consented patient cohort and write consented_patients_analysis.csv
	$(PYTHON) scripts/analyze_consented_patients.py

ui:                            ## Launch Streamlit researcher portal
	@bash -c '$(JAVA_ENV_CMD) && \
		$(PYTHON) -m streamlit run apps/streamlit/researcher_ui.py -- \
		  --config $(CONFIG)'
