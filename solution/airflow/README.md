# Solution Airflow DAGs

Filled reference for the classroom Airflow lab. Student stubs: [`../../lab/airflow/`](../../lab/airflow/).

| DAG id | What |
| --- | --- |
| `solution_baseline_prep` | Merge → subset (~2000 rows) → baseline → publish `merged_latest.csv` |
| `solution_baseline_and_trigger` | Same prep + `trigger_solution_loop` stub (future gateway HTTP) |

One-shot prep without the UI:

```bash
docker compose -f infra/docker-compose.yml --env-file .env --profile airflow run --rm airflow-prep-once
```

Then open `/solution-loop`, pick `merged_latest.csv`, target `is_fraud`.
