"""Helpers for the adapted fraud research loop (lab/langgraph/graph.py).

New compared with loop_runtime.py:
  * load_from_warehouse  – read the Airflow-cleaned table straight from Postgres
  * leakage_scan         – data-driven leakage check (single-feature AUC), not just column names
  * baseline_scores      – majority / stratified dummy baselines on the exact same split
  * fit_eval             – probability model + F1-optimal threshold tuned on validation,
                           full metric set (accuracy, precision, recall, F1, ROC-AUC, PR-AUC)
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

WAREHOUSE_TABLE = os.getenv("WAREHOUSE_TABLE", "analytics.fraud_transactions")
LEAK_AUC = 0.95  # a single column this predictive on its own is treated as leakage


# ---------------------------------------------------------------------------
# Warehouse loader
# ---------------------------------------------------------------------------
def load_from_warehouse(out_csv: Path, dsn: str | None = None, table: str = WAREHOUSE_TABLE) -> dict:
    """Pull the cleaned table from Postgres into a CSV snapshot. Never raises."""
    dsn = dsn or os.getenv("WAREHOUSE_DSN", "").strip()
    if not dsn:
        return {"ok": False, "reason": "WAREHOUSE_DSN not set"}
    try:
        import psycopg2  # type: ignore
    except ImportError:
        return {"ok": False, "reason": "psycopg2 not installed"}
    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {table}")
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"warehouse unavailable: {str(exc).splitlines()[0][:160]}"}
    if not rows:
        return {"ok": False, "reason": f"{table} is empty — run the Airflow DAG first"}
    df = pd.DataFrame(rows, columns=cols)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    return {"ok": True, "path": str(out_csv), "rows": len(df), "columns": len(cols), "table": table}


# ---------------------------------------------------------------------------
# Data-driven leakage scan
# ---------------------------------------------------------------------------
def _looks_like_datetime(s: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if pd.api.types.is_numeric_dtype(s):
        return False
    sample = s.dropna().astype(str).head(50)
    if sample.empty or not sample.str.contains(r"\d{4}-\d{2}-\d{2}").all():
        return False
    return pd.to_datetime(sample, errors="coerce").notna().mean() > 0.9


def leakage_scan(df: pd.DataFrame, target: str) -> dict:
    """Flag (a) columns that alone predict the target almost perfectly, (b) ids, (c) raw datetimes."""
    y = df[target]
    leaks, ids, dates, single_auc = [], [], [], {}
    binary = y.nunique() == 2
    for c in df.columns:
        if c == target:
            continue
        s = df[c]
        if c.lower().endswith("_id") or c.lower() == "id":
            ids.append(c)
            continue
        if _looks_like_datetime(s):
            dates.append(c)
            continue
        if not pd.api.types.is_numeric_dtype(s):
            if s.nunique(dropna=True) > 0.9 * len(s):
                ids.append(c)
            continue
        if binary and s.notna().sum() > 10:
            filled = s.fillna(s.median())
            try:
                auc = float(roc_auc_score(y, filled))
            except ValueError:
                continue
            auc = max(auc, 1 - auc)
            single_auc[c] = round(auc, 4)
            if auc >= LEAK_AUC:
                leaks.append(c)
    top = dict(sorted(single_auc.items(), key=lambda kv: -kv[1])[:8])
    return {
        "leaky_columns": leaks,
        "id_columns": ids,
        "datetime_columns": dates,
        "drops": sorted(set(leaks + ids + dates)),
        "top_single_feature_auc": top,
    }


# ---------------------------------------------------------------------------
# Splits, models, metrics
# ---------------------------------------------------------------------------
def split(df: pd.DataFrame, target: str, drops: list[str], seed: int, holdout_frac: float):
    """Same 3-way split as loop_runtime._fit_score: train / val (inner 25%) / sealed holdout."""
    y = df[target].astype(int)
    X = df.drop(columns=[target, *[c for c in drops if c in df.columns and c != target]])
    X_tmp, X_hold, y_tmp, y_hold = train_test_split(
        X, y, test_size=holdout_frac, random_state=seed, stratify=y
    )
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_tmp, y_tmp, test_size=0.25, random_state=seed, stratify=y_tmp
    )
    return X_tmp, y_tmp, X_tr, y_tr, X_val, y_val, X_hold, y_hold


def build_model(family: str, hp: dict, seed: int = 42):
    hp = dict(hp or {})
    if family == "logistic_regression":
        return LogisticRegression(
            C=float(hp.get("C", 1.0)), max_iter=int(hp.get("max_iter", 1000)), class_weight="balanced"
        )
    if family == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=float(hp.get("learning_rate", 0.1)),
            max_iter=int(hp.get("max_iter", 100)),
            max_depth=hp.get("max_depth"),
            class_weight="balanced",
            random_state=seed,
        )
    depth = hp.get("max_depth", 6)
    return RandomForestClassifier(
        n_estimators=int(hp.get("n_estimators", 200)),
        max_depth=None if depth in (None, "None", 0) else int(depth),
        min_samples_leaf=int(hp.get("min_samples_leaf", 3)),
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=-1,
    )


def _pipe(model, X: pd.DataFrame) -> Pipeline:
    num = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat = [c for c in X.columns if c not in num]
    pre = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
            (
                "cat",
                Pipeline(
                    [("imp", SimpleImputer(strategy="most_frequent")), ("oh", OneHotEncoder(handle_unknown="ignore"))]
                ),
                cat,
            ),
        ]
    )
    return Pipeline([("pre", pre), ("clf", model)])


def metrics_at(y_true, proba, threshold: float) -> dict:
    pred = (np.asarray(proba) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    out = {
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "threshold": float(threshold),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }
    try:
        out["roc_auc"] = float(roc_auc_score(y_true, proba))
        out["pr_auc"] = float(average_precision_score(y_true, proba))
    except ValueError:
        out["roc_auc"] = out["pr_auc"] = None
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items()}


def best_f1_threshold(y_true, proba) -> float:
    prec, rec, thr = precision_recall_curve(y_true, proba)
    if len(thr) == 0:
        return 0.5
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-12, None)
    return float(thr[int(np.nanargmax(f1))])


def baseline_scores(df: pd.DataFrame, target: str, drops: list[str], seed: int, holdout_frac: float) -> dict:
    _, _, X_tr, y_tr, X_val, y_val, _, _ = split(df, target, drops, seed, holdout_frac)
    out = {"prevalence": round(float(y_tr.mean()), 4)}
    for name in ("most_frequent", "stratified"):
        d = DummyClassifier(strategy=name, random_state=seed).fit(X_tr, y_tr)
        p = d.predict_proba(X_val)[:, 1]
        out[name] = metrics_at(y_val, p, 0.5)
    # "Flag everything as fraud": recall 1, the F1 floor a tuned threshold can always reach.
    out["always_positive"] = metrics_at(y_val, np.ones(len(y_val)), 0.5)
    return out


def fit_eval(
    df: pd.DataFrame,
    target: str,
    spec: dict,
    seed: int,
    holdout_frac: float,
    *,
    on_holdout: bool,
    threshold: float | None = None,
) -> dict:
    """Train + score one ExperimentSpec.

    Validation mode: train on train split, tune the F1-optimal threshold on val, report val metrics.
    Holdout mode:    train on train+val, score the sealed holdout with the val-tuned threshold.
    """
    drops = list(spec.get("drop_columns") or [])
    X_tmp, y_tmp, X_tr, y_tr, X_val, y_val, X_hold, y_hold = split(df, target, drops, seed, holdout_frac)
    family = str(spec.get("model_family") or "logistic_regression")
    model = build_model(family, spec.get("hyperparameters") or {}, seed)
    t0 = time.time()
    if on_holdout:
        pipe = _pipe(model, X_tmp).fit(X_tmp, y_tmp)
        proba = pipe.predict_proba(X_hold)[:, 1]
        m = metrics_at(y_hold, proba, 0.5 if threshold is None else threshold)
        m["n_holdout"] = int(len(y_hold))
        m["model_family"] = family
        return m
    pipe = _pipe(model, X_tr).fit(X_tr, y_tr)
    proba = pipe.predict_proba(X_val)[:, 1]
    thr = best_f1_threshold(y_val, proba)
    m = metrics_at(y_val, proba, thr)
    m["f1_at_0.5"] = metrics_at(y_val, proba, 0.5)["f1"]
    dur = round(time.time() - t0, 3)
    return {
        "status": "succeeded",
        "experiment_id": spec.get("experiment_id"),
        "model_family": family,
        "hyperparameters": spec.get("hyperparameters") or {},
        "drop_columns": [c for c in drops if c in df.columns],
        "validation_metrics": m,
        "threshold": m["threshold"],
        "duration_sec": dur,
        "duration_seconds": dur,
        "n_train": int(len(y_tr)),
        "n_val": int(len(y_val)),
        "n_holdout": int(len(y_hold)),
    }
