"""Assignment DAG — scheduled fraud ETL → Postgres warehouse → analysis.

    ┌ customers    : extract → clean → quality_check → load_staging ┐
    ├ transactions : extract → clean → quality_check → load_staging ┼→ merge_datasets → load_warehouse
    └ merchants    : extract → clean → quality_check → load_staging ┘                         │
                                    ┌─────────────────────────────────────────────────────────┤
                                    │  analysis.train_models  (reads Postgres, trains, scores) │
                                    │  analysis.eda_charts    (reads Postgres, plots)          ├→ write_report
                                    │  publish_agent_dataset  (Postgres → CSV for LangGraph)   │
                                    └──────────────────────────────────────────────────────────┘

* Schedule: daily at 06:00 UTC (`catchup=False`, one active run at a time).
* Parallelism: the three dataset TaskGroups run side by side (LocalExecutor), and the
  three analysis/publish tasks fan out after the warehouse load.
* Transform logic lives in `pipeline/fraud_etl.py` so it can be tested without Airflow.
* Warehouse: Postgres service `warehouse-db`, Airflow connection id `warehouse_db`
  (set by AIRFLOW_CONN_WAREHOUSE_DB in infra/docker-compose.yml).
"""

from __future__ import annotations

import io
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.utils.task_group import TaskGroup

from pipeline import fraud_etl as etl

REPO = Path("/repo")
RAW_DIR = REPO / "datasets" / "airflow"
RUNS = REPO / "artifacts" / "airflow" / "fraud_runs"
REPORTS = REPO / "reports" / "fraud_pipeline"
AGENT_DATASET = REPO / "datasets" / "airflow" / "fraud_clean.csv"
CONN_ID = "warehouse_db"
WAREHOUSE_TABLE = "analytics.fraud_transactions"

SOURCES = {
    # name: (raw file, primary key, cleaner)
    "customers": ("customers.csv", "customer_id", etl.clean_customers),
    "transactions": ("transactions.csv", "transaction_id", etl.clean_transactions),
    "merchants": ("merchants.csv", "merchant_id", etl.clean_merchants),
}


# ---------------------------------------------------------------------------
# Postgres helpers
# ---------------------------------------------------------------------------
def _write_table(df: pd.DataFrame, table: str, pk: str | None = None, replace: bool = True) -> int:
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    conn = hook.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS staging; CREATE SCHEMA IF NOT EXISTS analytics;")
            cur.execute(etl.create_table_sql(df, table, pk, replace))
            cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv)", io.StringIO(etl.to_copy_csv(df)))
        conn.commit()
    finally:
        conn.close()
    return len(df)


def _read_table(sql: str) -> pd.DataFrame:
    hook = PostgresHook(postgres_conn_id=CONN_ID)
    conn = hook.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    for c in df.columns:  # NUMERIC/None → proper numeric dtype
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            conv = pd.to_numeric(df[c], errors="coerce")
            if conv.notna().sum() == df[c].notna().sum() and df[c].notna().any():
                df[c] = conv
    return df


def _run_dir(context) -> Path:
    d = RUNS / context["ts_nodash"]
    d.mkdir(parents=True, exist_ok=True)
    return d


@dag(
    dag_id="fraud_etl_pipeline",
    description="3 related tables → clean (parallel TaskGroups) → merge → Postgres → analysis",
    start_date=datetime(2026, 11, 1),
    schedule="0 6 * * *",  # every day at 06:00 UTC
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"owner": "laura", "retries": 2, "retry_delay": timedelta(seconds=10)},
    tags=["assignment", "etl", "postgres", "fraud"],
)
def fraud_etl_pipeline():
    # ---------------- per-dataset tasks (reused inside each TaskGroup) ----------------
    @task
    def extract(name: str, **context) -> str:
        """Ingest: copy the raw source file into this run's folder (immutable snapshot)."""
        src = RAW_DIR / SOURCES[name][0]
        if not src.is_file():
            raise FileNotFoundError(src)
        dst = _run_dir(context) / f"raw_{name}.csv"
        shutil.copyfile(src, dst)
        return str(dst)

    @task
    def clean(name: str, raw_path: str, **context) -> str:
        cleaner = SOURCES[name][2]
        df = cleaner(pd.read_csv(raw_path))
        out = _run_dir(context) / f"clean_{name}.pkl"
        df.to_pickle(out)
        return str(out)

    @task
    def quality_check(name: str, clean_path: str) -> dict:
        report = etl.quality_report(pd.read_pickle(clean_path), name, SOURCES[name][1])
        etl.assert_quality(report)  # fails the task (and retries) on bad keys / empty table
        return report

    @task
    def load_staging(name: str, clean_path: str, report: dict) -> dict:
        n = _write_table(pd.read_pickle(clean_path), f"staging.{name}", SOURCES[name][1])
        return {**report, "loaded_rows": n, "table": name}

    # ---------------- merge + load ----------------
    @task
    def merge_datasets(customers: str, transactions: str, merchants: str, **context) -> str:
        merged = etl.merge_all(
            pd.read_pickle(transactions), pd.read_pickle(customers), pd.read_pickle(merchants)
        )
        out = _run_dir(context) / "merged.pkl"
        merged.to_pickle(out)
        return str(out)

    @task
    def load_warehouse(merged_path: str) -> dict:
        df = pd.read_pickle(merged_path)
        n = _write_table(df, WAREHOUSE_TABLE, "transaction_id")
        return {"table": WAREHOUSE_TABLE, "rows": n, "fraud_rate": round(float(df[etl.TARGET].mean()), 4)}

    # ---------------- analysis (reads back from Postgres) ----------------
    @task
    def train_models(_load: dict, **context) -> dict:
        df = _read_table(f"SELECT * FROM {WAREHOUSE_TABLE}")
        analysis = etl.train_models(df)
        out = REPORTS / context["ts_nodash"]
        charts = etl.model_charts(analysis, out)
        analysis.pop("_curves", None)
        metrics = pd.DataFrame(analysis["models"])
        metrics["run_ts"] = context["ts"]
        _write_table(metrics, "analytics.model_metrics", replace=False)  # history across runs
        (out / "metrics.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
        return {**analysis, "charts": charts}

    @task
    def eda_charts(_load: dict, **context) -> list[str]:
        df = _read_table(
            f"SELECT merchant_category_master, fraud_probability, log_amount, {etl.TARGET} "
            f"FROM {WAREHOUSE_TABLE}"
        )
        return etl.make_charts(df, REPORTS / context["ts_nodash"])

    @task
    def publish_agent_dataset(_load: dict) -> dict:
        """Hand-off to Part 2: export the cleaned warehouse table for the LangGraph loop."""
        df = _read_table(f"SELECT * FROM {WAREHOUSE_TABLE} ORDER BY transaction_id")
        df.to_csv(AGENT_DATASET, index=False)
        return {"path": str(AGENT_DATASET), "rows": len(df), "target": etl.TARGET}

    @task
    def write_report(quality: list[dict], analysis: dict, eda: list[str], publish: dict, **context) -> str:
        out = REPORTS / context["ts_nodash"]
        charts = list(eda) + list(analysis.get("charts") or [])
        md = etl.report_markdown(quality, analysis, charts, context["run_id"])
        md += f"\nAgent dataset published: `{publish['path']}` ({publish['rows']} rows)\n"
        (out / "report.md").write_text(md, encoding="utf-8")
        latest = REPORTS / "latest"
        shutil.rmtree(latest, ignore_errors=True)
        shutil.copytree(out, latest)
        return str(latest / "report.md")

    # ---------------- wiring ----------------
    cleaned, loaded = {}, []
    for name in SOURCES:
        with TaskGroup(group_id=name, tooltip=f"ingest + clean {name}"):
            raw = extract(name)
            path = clean(name, raw)
            q = quality_check(name, path)
            loaded.append(load_staging(name, path, q))
            cleaned[name] = path

    merged = merge_datasets(cleaned["customers"], cleaned["transactions"], cleaned["merchants"])
    wh = load_warehouse(merged)
    loaded >> merged  # merge only after every staging load + quality gate passed

    with TaskGroup(group_id="analysis", tooltip="read from Postgres, model + visualise"):
        analysis = train_models(wh)
        eda = eda_charts(wh)
    publish = publish_agent_dataset(wh)
    write_report(loaded, analysis, eda, publish)


fraud_etl_pipeline()
