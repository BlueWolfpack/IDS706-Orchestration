# Student Guide (`/guide`) — Airflow tab design

Date: 2026-11-04  
Status: approved for planning (Airflow first; LangGraph placeholder)

## Goal

A static stepped page in the existing frontend that walks students through the Airflow classroom lab: start Docker Airflow, fill `student_baseline_prep.py` from per-task copy snippets, wire the DAG, then Trigger in the UI.

## Non-goals (this pass)

- LangGraph tab content (placeholder only)
- Progress checkboxes / localStorage
- Live verification against the Airflow API
- Full-file “paste the whole solution” dump
- Separate guide app or new port

## Placement

| Item | Choice |
| --- | --- |
| Route | `/guide` |
| App | Existing Vite/React frontend |
| Tabs | **Airflow** (built now) · **LangGraph** (“Next lab” stub) |
| Discoverability | Link from app nav (and/or projects landing) |

Outbound links:

- Airflow UI: `http://localhost:8088` (login `admin` / `admin` unless `.env` overrides)
- Skeleton path: `airflow/dags/student_baseline_prep.py`
- Reference: `airflow/dags/simple_loop_baseline_prep.py` (all logic inside `@task` bodies; no helper modules)

## Airflow tab structure

Numbered sections, top to bottom. Each command/snippet block has a **Copy** control.

### 1. Start Airflow

From repo root:

1. Ensure Docker Desktop is running
2. `cp .env.example .env` if `.env` is missing (optional keys not required for this DAG)
3. Start profile:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow up --build -d
```

4. Open `http://localhost:8088` → login
5. Confirm DAGs include `student_baseline_prep` (lab) and `simple_loop_baseline_prep` (filled reference)

Note: Do not install Airflow on the host; Docker only.

### 2. Open the skeleton

- File: `airflow/dags/student_baseline_prep.py`
- Behavior until wired: DAG parses; Graph tab is empty
- Do not Trigger until Phase 2 wiring is uncommented and task bodies return real helpers

### 3. Fill task bodies (one snippet per task)

Order matches the skeleton TODOs:

1. Fill each `@task` body with inline pandas/sklearn (copy from reference / guide snippets)
2. `validate_customers` → `return task_validate_customers(**context)`
3. `validate_transactions` → `return task_validate_transactions(**context)`
4. `merge_csvs` → `return task_merge_csvs(left_meta, right_meta, **context)`
5. `make_subset` → `return task_make_subset(merge_meta, **context)`
6. `profile_light` → `return task_profile_light(subset_meta, **context)`
7. `train_baseline` → `return task_train_baseline(subset_meta, profile_meta, **context)`
8. `publish_merged` → `return task_publish_merged(subset_meta, baseline, **context)`

UI: one card per item — short hint + fenced snippet + Copy. Snippets are the full `@task` bodies from `simple_loop_baseline_prep.py`.

### 4. Wire the DAG

One copyable block (Phase 2 in the skeleton):

```python
left = validate_customers()
right = validate_transactions()
merged = merge_csvs(left, right)
demo = make_subset(merged)
prof = profile_light(demo)
base = train_baseline(demo, prof)
publish_merged(demo, base)
```

After save, Graph tab should show the full dependency graph (via the mounted `airflow/dags` volume).

### 5. Run in Airflow

1. Unpause `student_baseline_prep`
2. Trigger DAG
3. Wait for green success on Graph
4. Confirm publish output: `datasets/airflow/merged_latest.csv` (and run artifacts under `artifacts/airflow/runs/<run_id>/`)

## LangGraph tab (stub)

Placeholder copy only, e.g. “Next lab — LangGraph simple loop.” No steps in this pass.

## Implementation notes (for the plan)

- Prefer one page component (e.g. `GuidePage`) + small presentational pieces (tab strip, step section, copyable code block)
- Snippet source of truth: either inline constants next to the page or a dedicated `guide/airflowSnippets.ts` — keep in sync with `student_baseline_prep.py`
- Reuse existing visual language (lab-grid, fonts, borders); avoid a second design system
- No new backend endpoints

## Success criteria

- Student can follow `/guide` Airflow tab without reading `airflow/README.md`
- Copy buttons yield pasteable snippets that complete the skeleton
- After wiring + Trigger, prep publishes `merged_latest.csv` the same way as the reference DAG
