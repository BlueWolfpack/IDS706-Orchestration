"""Shared merge + baseline prep for Airflow DAGs and CLI (no Airflow import).

Classroom order:
  1) Run this prep (via Airflow DAG 1 or `python -m solution.langgraph.baseline`)
  2) Run the solution research loop standalone on merged.csv
  3) Later: DAG 2 stubs the Airflow → loop trigger
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

REPO = Path(__file__).resolve().parents[2]
DEFAULT_LEFT = REPO / "datasets" / "airflow" / "customers.csv"
DEFAULT_RIGHT = REPO / "datasets" / "airflow" / "transactions.csv"
DEFAULT_OUT = REPO / "artifacts" / "airflow" / "runs"
ID_LIKE = {
    "customer_id",
    "transaction_id",
    "merchant_id",
    "card_id",
    "device_id",
    "timestamp",
    "IP_country",
}


def validate_csv(path: str | Path, *, require_columns: list[str]) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"CSV not found: {p}")
    df = pd.read_csv(p, nrows=5)
    missing = [c for c in require_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{p.name} missing columns: {missing}")
    n = sum(1 for _ in p.open(encoding="utf-8", errors="replace")) - 1
    return {
        "path": str(p.resolve()),
        "filename": p.name,
        "n_rows_est": max(n, 0),
        "columns": list(pd.read_csv(p, nrows=0).columns),
        "require_columns": require_columns,
    }


def merge_csvs(
    left_path: str | Path,
    right_path: str | Path,
    *,
    join_key: str = "customer_id",
    how: str = "left",
    target_column: str = "is_fraud",
    seed: int = 42,
    out_csv: str | Path,
) -> dict[str, Any]:
    """Merge fact (right/transactions) with dim (left/customers). Target stays on fact."""
    del seed  # kept for call-site compatibility; merge is deterministic
    left = pd.read_csv(left_path)
    right = pd.read_csv(right_path)
    if join_key not in left.columns or join_key not in right.columns:
        raise ValueError(f"join_key {join_key!r} must exist on both CSVs")
    if target_column not in right.columns:
        raise ValueError(f"target {target_column!r} must exist on transactions CSV")

    # Prefer fact-left so one row per transaction: transactions ⟕ customers
    merged = right.merge(left, on=join_key, how=how, suffixes=("", "_customer"))

    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out, index=False)

    return {
        "merged_path": str(out.resolve()),
        "join_key": join_key,
        "how": how,
        "n_left": int(len(left)),
        "n_right": int(len(right)),
        "n_merged": int(len(merged)),
        "target_column": target_column,
        "target_rate": float(merged[target_column].mean())
        if pd.api.types.is_numeric_dtype(merged[target_column])
        else None,
    }


def make_subset(
    merged_path: str | Path,
    *,
    out_csv: str | Path,
    n_rows: int = 2000,
    target_column: str = "is_fraud",
    seed: int = 42,
) -> dict[str, Any]:
    """Write a small stratified demo table so baseline + simple loop train quickly."""
    df = pd.read_csv(merged_path)
    if target_column not in df.columns:
        raise ValueError(f"target {target_column!r} missing from merged CSV")
    n = min(int(n_rows), len(df))
    if n < len(df) and df[target_column].nunique() >= 2:
        # Proportional sample per class (keeps fraud rate ≈ full table).
        parts: list[pd.DataFrame] = []
        rng = seed
        remaining = n
        groups = list(df.groupby(target_column, sort=True))
        for i, (_, g) in enumerate(groups):
            if i == len(groups) - 1:
                take = min(len(g), remaining)
            else:
                take = min(len(g), max(1, int(round(n * len(g) / len(df)))))
                take = min(take, remaining - (len(groups) - 1 - i))
            parts.append(g.sample(n=take, random_state=rng))
            remaining -= take
            rng += 1
        subset = pd.concat(parts, ignore_index=True)
        if len(subset) > n:
            subset = subset.sample(n=n, random_state=seed).reset_index(drop=True)
    elif n < len(df):
        subset = df.sample(n=n, random_state=seed).reset_index(drop=True)
    else:
        subset = df.reset_index(drop=True)

    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    subset.to_csv(out, index=False)
    return {
        "subset_path": str(out.resolve()),
        # Downstream tasks expect a "table path" key — use subset as the training table.
        "merged_path": str(out.resolve()),
        "full_merged_path": str(Path(merged_path).resolve()),
        "n_source": int(len(df)),
        "n_subset": int(len(subset)),
        "target_column": target_column,
        "target_rate": float(subset[target_column].mean())
        if pd.api.types.is_numeric_dtype(subset[target_column])
        else None,
    }


def profile_light(merged_path: str | Path, target_column: str = "is_fraud") -> dict[str, Any]:
    df = pd.read_csv(merged_path)
    if target_column not in df.columns:
        raise ValueError(f"target {target_column!r} missing from merged CSV")
    cols = list(df.columns)
    leakage = [
        c
        for c in cols
        if c != target_column
        and (
            c in ID_LIKE
            or c.lower().endswith("_id")
            or c.lower() in {"name", "email", "ip_country"}
        )
    ]
    # Fraud probability is a leaky label proxy — never train on it.
    for leak in ("fraud_probability", "fraud_history"):
        if leak in df.columns and leak not in leakage and leak != target_column:
            leakage.append(leak)

    num = [c for c in cols if c != target_column and pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in cols if c != target_column and c not in num and c not in leakage]
    return {
        "n_rows": int(len(df)),
        "n_columns": int(len(cols)),
        "target": target_column,
        "target_rate": float(df[target_column].mean())
        if pd.api.types.is_numeric_dtype(df[target_column])
        else None,
        "numeric_features": num,
        "categorical_features": cat,
        "leakage_suspects": leakage,
        "recommended_drops": leakage,
        "notes": [
            "Light profile for Airflow baseline (no LLM).",
            "Drop id-like columns and fraud_probability before modeling.",
        ],
    }


def _build_model(family: str, hp: dict[str, Any]):
    if family == "logistic_regression":
        return LogisticRegression(
            C=float(hp.get("C", 1.0)),
            max_iter=int(hp.get("max_iter", 500)),
            class_weight=hp.get("class_weight", "balanced"),
        )
    if family == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=float(hp.get("learning_rate", 0.1)),
            max_iter=int(hp.get("max_iter", 100)),
        )
    return RandomForestClassifier(
        n_estimators=int(hp.get("n_estimators", 100)),
        max_depth=hp.get("max_depth", 6),
        class_weight=hp.get("class_weight", "balanced"),
        random_state=42,
    )


def train_baseline(
    merged_path: str | Path,
    *,
    target_column: str = "is_fraud",
    drop_columns: list[str] | None = None,
    model_family: str = "logistic_regression",
    hyperparameters: dict[str, Any] | None = None,
    seed: int = 42,
    holdout_frac: float = 0.2,
    experiment_id: str = "baseline-lr",
) -> dict[str, Any]:
    """Train one baseline with the same split convention as solution langgraph ml_engineer.

    Holdout is sealed first and never scored here.
    """
    df = pd.read_csv(merged_path)
    if target_column not in df.columns:
        raise ValueError(f"target {target_column!r} missing")

    hp = dict(hyperparameters or {"C": 1.0, "max_iter": 200})
    drops = [c for c in (drop_columns or []) if c in df.columns and c != target_column]
    y = df[target_column]
    X = df.drop(columns=[target_column, *drops], errors="ignore")

    strat = y if y.nunique() >= 2 and y.value_counts().min() >= 2 else None
    X_tmp, X_hold, y_tmp, y_hold = train_test_split(
        X, y, test_size=holdout_frac, random_state=seed, stratify=strat
    )
    strat2 = y_tmp if y_tmp.nunique() >= 2 and y_tmp.value_counts().min() >= 2 else None
    X_train, X_val, y_train, y_val = train_test_split(
        X_tmp, y_tmp, test_size=0.25, random_state=seed, stratify=strat2
    )

    num_cols = [c for c in X_train.columns if pd.api.types.is_numeric_dtype(X_train[c])]
    # Cap cardinality so OHE stays tractable in the teaching DAG.
    cat_cols = [
        c
        for c in X_train.columns
        if c not in num_cols and X_train[c].nunique(dropna=True) <= 40
    ]
    pre = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), num_cols),
            (
                "cat",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="most_frequent")),
                        (
                            "oh",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                sparse_output=False,
                            ),
                        ),
                    ]
                ),
                cat_cols,
            ),
        ]
    )
    model = _build_model(model_family, hp)
    pipe = Pipeline([("pre", pre), ("clf", model)])
    t0 = time.time()
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_val)
    duration = time.time() - t0

    spec = {
        "experiment_id": experiment_id,
        "model_family": model_family,
        "hyperparameters": hp,
        "drop_columns": drops,
        "rationale": "Airflow A-baseline on customer⨝transaction fraud table",
    }
    metrics = {
        "f1": float(f1_score(y_val, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_val, pred)),
    }
    return {
        "baseline_spec": spec,
        "baseline_validation_metrics": metrics,
        "n_train": int(len(X_train)),
        "n_val": int(len(X_val)),
        "n_holdout": int(len(X_hold)),
        "duration_sec": round(duration, 3),
        "seed": seed,
        "holdout_frac": holdout_frac,
        # Explicit: holdout unused
        "holdout_scored": False,
    }


def publish_merged(
    *,
    run_id: str,
    merged_path: str | Path,
    baseline: dict[str, Any],
    target_column: str = "is_fraud",
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Publish the demo training table (usually subset.csv) as merged_latest.csv for the UI."""
    del out_dir  # run artifacts already written by merge/subset tasks
    table = Path(merged_path)
    if not table.is_file():
        raise FileNotFoundError(f"demo table missing: {table}")

    pub = REPO / "datasets" / "airflow" / "merged_latest.csv"
    pub.parent.mkdir(parents=True, exist_ok=True)
    pub.write_bytes(table.read_bytes())

    f1 = float((baseline.get("baseline_validation_metrics") or {}).get("f1") or 0)
    return {
        "merged_dataset_path": str(table.resolve()),
        "published_latest": str(pub.resolve()),
        "baseline_val_f1": f1,
        "target_column": target_column,
        "run_id": run_id,
    }


def run_prep(
    *,
    left_path: str | Path = DEFAULT_LEFT,
    right_path: str | Path = DEFAULT_RIGHT,
    join_key: str = "customer_id",
    how: str = "left",
    target_column: str = "is_fraud",
    seed: int = 42,
    holdout_frac: float = 0.2,
    baseline_family: str = "logistic_regression",
    subset_rows: int = 2000,
    run_id: str | None = None,
) -> dict[str, Any]:
    rid = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = DEFAULT_OUT / rid
    out_dir.mkdir(parents=True, exist_ok=True)

    left_meta = validate_csv(left_path, require_columns=[join_key])
    right_meta = validate_csv(
        right_path, require_columns=[join_key, target_column]
    )
    merge_meta = merge_csvs(
        left_path,
        right_path,
        join_key=join_key,
        how=how,
        target_column=target_column,
        seed=seed,
        out_csv=out_dir / "merged.csv",
    )
    subset_meta = make_subset(
        merge_meta["merged_path"],
        out_csv=out_dir / "subset.csv",
        n_rows=subset_rows,
        target_column=target_column,
        seed=seed,
    )
    profile = profile_light(subset_meta["merged_path"], target_column=target_column)
    baseline = train_baseline(
        subset_meta["merged_path"],
        target_column=target_column,
        drop_columns=list(profile.get("recommended_drops") or []),
        model_family=baseline_family,
        hyperparameters=(
            {"C": 1.0, "max_iter": 500, "class_weight": "balanced"}
            if baseline_family == "logistic_regression"
            else {"n_estimators": 100, "max_depth": 6, "class_weight": "balanced"}
            if baseline_family == "random_forest"
            else {"learning_rate": 0.1, "max_iter": 100}
        ),
        seed=seed,
        holdout_frac=holdout_frac,
    )
    published = publish_merged(
        run_id=rid,
        merged_path=subset_meta["merged_path"],
        baseline=baseline,
        target_column=target_column,
        out_dir=out_dir,
    )
    return {
        "left": left_meta,
        "right": right_meta,
        "merge": merge_meta,
        "subset": subset_meta,
        "profile": profile,
        "baseline": baseline,
        "published": published,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Merge customers⨝transactions + train baseline")
    p.add_argument("--left", default=str(DEFAULT_LEFT))
    p.add_argument("--right", default=str(DEFAULT_RIGHT))
    p.add_argument("--join-key", default="customer_id")
    p.add_argument("--how", default="left")
    p.add_argument("--target", default="is_fraud")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--holdout-frac", type=float, default=0.2)
    p.add_argument("--family", default="logistic_regression")
    p.add_argument("--subset-rows", type=int, default=2000)
    p.add_argument("--run-id", default=None)
    args = p.parse_args()
    result = run_prep(
        left_path=args.left,
        right_path=args.right,
        join_key=args.join_key,
        how=args.how,
        target_column=args.target,
        seed=args.seed,
        holdout_frac=args.holdout_frac,
        baseline_family=args.family,
        subset_rows=args.subset_rows,
        run_id=args.run_id,
    )
    print(json.dumps(
        {
            "merged_dataset_path": result["published"]["merged_dataset_path"],
            "published_latest": result["published"]["published_latest"],
            "baseline_val_f1": result["published"]["baseline_val_f1"],
            "n_merged": result["merge"]["n_merged"],
            "n_subset": result["subset"]["n_subset"],
            "target_column": result["published"]["target_column"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
