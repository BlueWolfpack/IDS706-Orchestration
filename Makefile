COMPOSE := docker compose -f infra/docker-compose.yml --env-file .env
VENV := .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: fraud-dag warehouse-psql test-assignment
.PHONY: ensure-env up down down-mac down-windows logs test install health venv \
	demo-sse rebuild-gateway frontend start start-mac start-windows airflow

ensure-env:
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example")

# ---------------------------------------------------------------------------
# Web app — pick your OS (start is the same; down kills Vite differently)
# ---------------------------------------------------------------------------

start:
	@echo ""
	@echo "  Use one of:"
	@echo "    make start-mac        # macOS"
	@echo "    make start-windows    # Windows (run from Git Bash)"
	@echo ""
	@exit 1

down:
	@echo ""
	@echo "  Use one of:"
	@echo "    make down-mac         # macOS (kills Vite via lsof + Docker down)"
	@echo "    make down-windows     # Windows (kills Vite via PowerShell + Docker down)"
	@echo ""
	@exit 1

# Docker stack + Vite UI (blocks on npm run dev). Same on both OSes.
start-mac: ensure-env
	$(COMPOSE) up --build -d
	@echo "Waiting for gateway on :8000..."
	@i=0; while [ $$i -lt 36 ]; do \
	  if curl -sf http://127.0.0.1:8000/healthz >/dev/null; then echo "gateway ok"; break; fi; \
	  i=$$((i+1)); sleep 5; \
	  if [ $$i -eq 36 ]; then echo "gateway not ready — try: make health / make logs"; exit 1; fi; \
	done
	@echo "Open http://127.0.0.1:5173"
	@echo "Stop with:  make down-mac  (macOS)  or  make down-windows  (Windows)"
	cd frontend && npm install && npm run dev

# Same as start-mac. On Windows: run from Git Bash (needs curl + Make).
start-windows: start-mac

frontend:
	cd frontend && npm run dev

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install -e ".[dev]"

up: ensure-env
	$(COMPOSE) up --build -d
	@echo "Waiting for service health..."
	@$(COMPOSE) ps

airflow: ensure-env
	$(COMPOSE) --profile airflow up --build -d
	@echo "Airflow starting (often 1–2 min). Check: $(COMPOSE) --profile airflow ps"
	@echo "UI: http://localhost:8088  (admin / admin unless .env overrides)"

down-mac: ensure-env
	@-pids=$$(lsof -tiTCP:5173 -sTCP:LISTEN 2>/dev/null); \
	if [ -n "$$pids" ]; then echo "Stopping Vite on :5173 ($$pids)"; kill $$pids 2>/dev/null || true; fi
	$(COMPOSE) --profile airflow down

down-windows: ensure-env
	@powershell.exe -NoProfile -File infra/down-windows.ps1
	$(COMPOSE) --profile airflow down

logs: ensure-env
	$(COMPOSE) logs -f --tail=100

test: install
	$(PYTHON) -m pytest tests/contract -q

rebuild-gateway: ensure-env
	$(COMPOSE) up --build -d gateway

health:
	@for port in 8000 8011 8002 8003 8004 8005 8006; do \
	  printf "localhost:%s -> " "$$port"; \
	  curl -sf "http://127.0.0.1:$$port/healthz" || printf "FAIL"; \
	  printf "\n"; \
	done

# Stage A1: create a mock session and stream SSE until done.
# Usage: make demo-sse SCENARIO=happy
SCENARIO ?= happy
demo-sse:
	@SID=$$(curl -sf -X POST http://127.0.0.1:8000/sessions \
	  -H 'Content-Type: application/json' \
	  -d '{"target_column":"churned","scenario":"$(SCENARIO)"}' | $(PYTHON) -c 'import sys,json; print(json.load(sys.stdin)["session_id"])'); \
	echo "session=$$SID scenario=$(SCENARIO)"; \
	curl -sf -N "http://127.0.0.1:8000/sessions/$$SID/events"

# ---------------------------------------------------------------------------
# Assignment: fraud ETL pipeline + adapted agent loop
# ---------------------------------------------------------------------------
# Unpause + trigger the scheduled DAG once (Airflow must be up: make airflow)
fraud-dag: ensure-env
	$(COMPOSE) --profile airflow exec airflow-scheduler airflow dags unpause fraud_etl_pipeline
	$(COMPOSE) --profile airflow exec airflow-scheduler airflow dags trigger fraud_etl_pipeline

# Open psql on the Postgres warehouse written by the DAG
warehouse-psql: ensure-env
	$(COMPOSE) exec warehouse-db psql -U warehouse -d warehouse

# Unit tests for the ETL transforms and the adapted agent loop (no Docker needed)
test-assignment:
	$(PYTHON) -m pytest tests/assignment tests/unit/test_lab_loop.py -q
