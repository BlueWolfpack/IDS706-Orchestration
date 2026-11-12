"""DAG 2 — Same prep as DAG 1, then a stub that will later call the solution loop.

Classroom reveal: replace trigger_solution_loop with a real HTTP call to the gateway.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import shutil

import pandas as pd
from airflow.decorators import dag, task
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

# ---------------------------------------------------------------------------
# Paths inside the Airflow containers (/repo is the mounted project root)
# ---------------------------------------------------------------------------
REPO = Path("/repo")
CUSTOMERS = REPO / "datasets" / "airflow" / "customers.csv"
TRANSACTIONS = REPO / "datasets" / "airflow" / "transactions.csv"
RUNS = REPO / "artifacts" / "airflow" / "runs"
PUBLISH = REPO / "datasets" / "airflow" / "merged_latest.csv"
TARGET = "is_fraud"
JOIN_KEY = "customer_id"
SUBSET_ROWS = 2000

DEFAULT_ARGS = {
    "retries": 2,
    "retry_delay": timedelta(seconds=5),
}


# @dag registers a pipeline definition with Airflow (id, schedule, tags).
# schedule=None → Trigger manually in the UI.
# default_args: retries=2 → failed tasks retry twice (5 sec apart).
@dag(
    dag_id="solution_baseline_and_trigger",
    description="Merge → subset → baseline → STUB trigger into solution loop",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["solution-loop", "baseline", "trigger-pending", "classroom"],
)
def solution_baseline_and_trigger():
    """Same prep graph as DAG 1, plus one extra stub task at the end."""

    # @task = one executable node. Return values travel via XCom to dependents.
    @task
    def validate_customers():
        """Check the customers CSV exists and has the join key."""
        if not CUSTOMERS.is_file():
            raise FileNotFoundError(CUSTOMERS)
        cols = list(pd.read_csv(CUSTOMERS, nrows=0).columns)
        if JOIN_KEY not in cols:
            raise ValueError(f"missing {JOIN_KEY}")
        return {"path": str(CUSTOMERS)}

    @task
    def validate_transactions():
        """Check the transactions CSV exists and has join key + target label."""
        if not TRANSACTIONS.is_file():
            raise FileNotFoundError(TRANSACTIONS)
        cols = list(pd.read_csv(TRANSACTIONS, nrows=0).columns)
        for need in (JOIN_KEY, TARGET):
            if need not in cols:
                raise ValueError(f"missing {need}")
        return {"path": str(TRANSACTIONS)}

    @task
    def merge_csvs(left_meta: dict, right_meta: dict, **context):
        """Join transactions ⟕ customers. One output row per transaction."""
        run_id = context["ts_nodash"]
        out = RUNS / run_id / "merged.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        left = pd.read_csv(left_meta["path"])
        right = pd.read_csv(right_meta["path"])
        merged = right.merge(left, on=JOIN_KEY, how="left", suffixes=("", "_customer"))
        merged.to_csv(out, index=False)
        return {"merged_path": str(out), "n_merged": len(merged)}

    @task
    def make_subset(merge_meta: dict, **context):
        """Downsample so baseline + the later simple-loop demo stay fast in class."""
        run_id = context["ts_nodash"]
        out = RUNS / run_id / "subset.csv"
        df = pd.read_csv(merge_meta["merged_path"])
        n = min(SUBSET_ROWS, len(df))
        subset = df.sample(n=n, random_state=42) if n < len(df) else df
        subset.to_csv(out, index=False)
        return {"merged_path": str(out), "n_subset": len(subset)}

    @task
    def profile_light(subset_meta: dict):
        """List columns that look leaky / id-like so training can drop them."""
        df = pd.read_csv(subset_meta["merged_path"])
        drops = [
            c
            for c in df.columns
            if c != TARGET
            and (c.endswith("_id") or c in {"timestamp", "fraud_probability", "fraud_history"})
        ]
        return {"recommended_drops": drops, "n_rows": len(df)}

    @task
    def train_baseline(subset_meta: dict, profile_meta: dict):
        """Tiny numeric-only LogisticRegression — a classroom A-baseline."""
        df = pd.read_csv(subset_meta["merged_path"])
        drops = list(profile_meta.get("recommended_drops") or [])
        y = df[TARGET]
        X = (
            df.drop(columns=[TARGET, *drops], errors="ignore")
            .select_dtypes("number")
            .fillna(0)
        )
        X_train, X_val, y_train, y_val = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y if y.nunique() > 1 else None,
        )
        clf = LogisticRegression(max_iter=500, class_weight="balanced")
        clf.fit(X_train, y_train)
        f1 = float(f1_score(y_val, clf.predict(X_val), zero_division=0))
        return {"f1": f1, "n_train": len(X_train), "n_val": len(X_val)}

    @task
    def publish_merged(subset_meta: dict, baseline: dict):
        """Copy the subset to a stable path the simple-loop UI can pick up."""
        PUBLISH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(subset_meta["merged_path"], PUBLISH)
        return {
            "published_latest": str(PUBLISH),
            "merged_dataset_path": subset_meta["merged_path"],
            "baseline_val_f1": baseline["f1"],
            "target_column": TARGET,
        }

    @task
    def trigger_solution_loop(published: dict):
        """STUB — logs the payload a real gateway call would send.

        Reveal later: POST http://gateway:8000/solution-loop/run with dataset_path.
        """
        payload = {
            "status": "stub",
            "dataset_path": published["published_latest"],
            "target_column": published["target_column"],
            "gateway_url": "http://gateway:8000",
            "baseline_val_f1": published["baseline_val_f1"],
        }
        print("[trigger_solution_loop STUB]", payload)
        return payload

    # Wiring: each assignment creates Graph edges via XCom dependencies.
    left = validate_customers()
    right = validate_transactions()
    merged = merge_csvs(left, right)
    demo = make_subset(merged)
    prof = profile_light(demo)
    base = train_baseline(demo, prof)
    out = publish_merged(demo, base)
    trigger_solution_loop(out)  # extra node vs DAG 1


# Register with Airflow.
solution_baseline_and_trigger()
