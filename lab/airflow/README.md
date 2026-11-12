# Lab Airflow DAGs

Student path starts here. Filled reference DAGs live under [`../../solution/airflow/`](../../solution/airflow/).

## Classroom sequence

1. **Lab DAG** — edit [`dags/lab_baseline_prep.py`](dags/lab_baseline_prep.py): fill task bodies, then wire deps. Graph tab stays **empty until wired**.
2. **Solution reveal (DAG 1)** — `solution_baseline_prep`: merge → subset → baseline → publish
3. **Lab LangGraph** — `/lab-loop` on the published CSV (or Titanic)
4. **Solution reveal** — `/solution-loop` (filled `solution/langgraph`)
5. **Reveal DAG 2** — `solution_baseline_and_trigger` stub

Everything runs in **Docker**. Do not install Airflow on the host.

## Start Airflow

From the repo root:

```bash
make airflow
```

UI: http://localhost:8088 — login `admin` / `admin`.

| DAG id | What |
| --- | --- |
| `lab_baseline_prep` | Student lab — stubs + empty Graph until wiring is uncommented |
| `solution_baseline_prep` | Solution: merge → subset → baseline → publish |
| `solution_baseline_and_trigger` | Same prep → `trigger_solution_loop` stub |

Copy steps: [`COPY_GUIDE.md`](COPY_GUIDE.md) or the in-app `/guide`.
