"""Pure-pandas transform + analysis helpers for the `fraud_etl_pipeline` Airflow DAG.

Keeping the logic here (instead of inside @task bodies) means every step can be
unit-tested without Airflow:  python -m pipeline.fraud_etl  runs the whole thing locally.

Datasets (Kaggle: Financial Transaction Intelligence Dataset 2026, CC BY-NC-SA 4.0):
  transactions.csv  fact table, 1 row per transaction, label `is_fraud`
  customers.csv     customer dimension  (join on customer_id)
  merchants.csv     merchant dimension  (join on merchant_id)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

TARGET = "is_fraud"

# Columns that must never be used as model features.
ID_COLUMNS = ["transaction_id", "customer_id", "merchant_id"]
# `fraud_probability` is an upstream score that encodes the label
# (is_fraud == fraud_probability > 0.4 in this dataset) -> label leakage.
LEAKY_COLUMNS = ["fraud_probability"]
NON_FEATURES = ID_COLUMNS + LEAKY_COLUMNS + ["timestamp", "customer_since", TARGET]

YES_NO = {"yes": 1, "no": 0, "true": 1, "false": 0, "y": 1, "n": 0}


# ---------------------------------------------------------------------------
# Generic cleaning helpers
# ---------------------------------------------------------------------------
def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object or pd.api.types.is_string_dtype(out[c]):
            out[c] = out[c].astype("string").str.strip()
            out[c] = out[c].replace({"": pd.NA})
    return out


def _yes_no_to_int(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.lower().map(YES_NO).astype("Int64")


def quality_report(df: pd.DataFrame, name: str, key: str) -> dict:
    """Small data-quality summary that each TaskGroup returns via XCom."""
    return {
        "table": name,
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "duplicate_keys": int(df[key].duplicated().sum()),
        "null_keys": int(df[key].isna().sum()),
        "null_cells": int(df.isna().sum().sum()),
    }


def assert_quality(report: dict, min_rows: int = 1) -> None:
    if report["rows"] < min_rows:
        raise ValueError(f"{report['table']}: only {report['rows']} rows")
    if report["duplicate_keys"] or report["null_keys"]:
        raise ValueError(f"{report['table']}: key problems {report}")


# ---------------------------------------------------------------------------
# Per-table cleaning
# ---------------------------------------------------------------------------
def clean_customers(raw: pd.DataFrame) -> pd.DataFrame:
    df = _strip_strings(raw).drop_duplicates("customer_id").dropna(subset=["customer_id"])
    # loan_status is blank for customers without a loan -> explicit category
    df["loan_status"] = df["loan_status"].fillna("No loan")
    df["customer_since"] = pd.to_datetime(df["customer_since"], errors="coerce")
    df["age"] = pd.to_numeric(df["age"], errors="coerce").clip(18, 100)
    df["credit_score"] = pd.to_numeric(df["credit_score"], errors="coerce").clip(300, 900)
    for c in ("annual_income", "avg_monthly_balance", "total_accounts"):
        df[c] = pd.to_numeric(df[c], errors="coerce").clip(lower=0)
    # city/state/country in this synthetic file are mutually inconsistent
    # (e.g. country=UK, state=Tamil Nadu) -> keep country only, drop the rest.
    df = df.drop(columns=["state", "city"], errors="ignore")
    df = df.rename(columns={"country": "customer_country", "risk_level": "customer_risk_level"})
    return df.reset_index(drop=True)


def clean_merchants(raw: pd.DataFrame) -> pd.DataFrame:
    df = _strip_strings(raw).drop_duplicates("merchant_id").dropna(subset=["merchant_id"])
    df["fraud_history"] = _yes_no_to_int(df["fraud_history"])
    df["online_store"] = _yes_no_to_int(df["online_store"])
    df["risk_score"] = pd.to_numeric(df["risk_score"], errors="coerce").clip(0, 1)
    # merchant_name is a unique label (Merchant_1 …) -> no signal, drop.
    df = df.drop(columns=["merchant_name", "city"], errors="ignore")
    df = df.rename(
        columns={
            "category": "merchant_category_master",
            "country": "merchant_country",
            "years_in_business": "merchant_years_in_business",
            "monthly_revenue": "merchant_monthly_revenue",
            "risk_score": "merchant_risk_score",
            "fraud_history": "merchant_fraud_history",
            "online_store": "merchant_online_store",
        }
    )
    return df.reset_index(drop=True)


def clean_transactions(raw: pd.DataFrame) -> pd.DataFrame:
    df = _strip_strings(raw).drop_duplicates("transaction_id").dropna(
        subset=["transaction_id", "customer_id", "merchant_id", TARGET]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["amount"] > 0]
    for c in ("weekend", "international"):
        df[c] = _yes_no_to_int(df[c])
    df[TARGET] = df[TARGET].astype(int)
    # Single-valued column (all INR) carries no information.
    if df["currency"].nunique() <= 1:
        df = df.drop(columns=["currency"])
    # Engineered behavioural features
    df["log_amount"] = np.log1p(df["amount"])
    df["amount_to_avg_30d"] = (df["amount"] / df["average_spending_30d"].replace(0, np.nan)).round(4)
    df["is_night"] = df["transaction_hour"].between(0, 5).astype(int)
    df["month"] = df["timestamp"].dt.month
    # merchant_category duplicates the merchant master; keep the master copy only.
    df = df.drop(columns=["merchant_category"], errors="ignore")
    df = df.rename(columns={"customer_risk": "customer_risk_band"})
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
def merge_all(tx: pd.DataFrame, cust: pd.DataFrame, merch: pd.DataFrame) -> pd.DataFrame:
    """transactions ⟕ customers ⟕ merchants — one row per transaction."""
    df = tx.merge(cust, on="customer_id", how="left", validate="many_to_one")
    df = df.merge(merch, on="merchant_id", how="left", validate="many_to_one")
    df["customer_tenure_days"] = (df["timestamp"] - df["customer_since"]).dt.days
    df["ip_country_mismatch"] = (df["IP_country"] != df["customer_country"]).astype(int)
    df["merchant_country_mismatch"] = (df["merchant_country"] != df["customer_country"]).astype(int)
    if len(df) != len(tx):
        raise ValueError("merge changed the row count")
    return df


def feature_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in NON_FEATURES]


# ---------------------------------------------------------------------------
# Postgres helpers (used by the DAG through psycopg2 / PostgresHook)
# ---------------------------------------------------------------------------
def pg_type(dtype) -> str:
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    return "TEXT"


def create_table_sql(
    df: pd.DataFrame, table: str, primary_key: str | None = None, replace: bool = True
) -> str:
    """DDL from a DataFrame. replace=True → full refresh; False → append-only history table."""
    cols = [f'"{c}" {pg_type(t)}' for c, t in df.dtypes.items()]
    if primary_key:
        cols.append(f'PRIMARY KEY ("{primary_key}")')
    body = f"CREATE TABLE IF NOT EXISTS {table} (\n  " + ",\n  ".join(cols) + "\n);"
    return (f"DROP TABLE IF EXISTS {table};\n" + body) if replace else body


def to_copy_csv(df: pd.DataFrame) -> str:
    """CSV text for COPY ... FROM STDIN (NULLs as empty)."""
    return df.to_csv(index=False, header=False, date_format="%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def _split(df: pd.DataFrame, cols: list[str], seed: int = 42):
    from sklearn.model_selection import train_test_split

    X, y = df[cols], df[TARGET].astype(int)
    return train_test_split(X, y, test_size=0.25, random_state=seed, stratify=y)


def _pipeline(model, X: pd.DataFrame):
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    num = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat = [c for c in X.columns if c not in num]
    pre = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), num),
            (
                "cat",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="most_frequent")),
                        ("oh", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                cat,
            ),
        ]
    )
    return Pipeline([("pre", pre), ("clf", model)])


def _metrics(y_true, proba, threshold: float = 0.5) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        average_precision_score,
        balanced_accuracy_score,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )

    pred = (proba >= threshold).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, pred)), 4),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 4),
        "pr_auc": round(float(average_precision_score(y_true, proba)), 4),
        "threshold": round(float(threshold), 4),
    }


def train_models(df: pd.DataFrame, seed: int = 42) -> dict:
    """Train a few simple models on honest features + a leakage check.

    Returns {"models": [...], "fraud_rate": ..., "feature_importance": {...}}.
    """
    from sklearn.dummy import DummyClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression

    cols = feature_columns(df)
    X_tr, X_te, y_tr, y_te = _split(df, cols, seed)
    candidates = {
        "majority_class_baseline": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": RandomForestClassifier(
            n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
            random_state=seed, n_jobs=-1,
        ),
    }
    results, curves, importances = [], {}, {}
    for name, model in candidates.items():
        pipe = _pipeline(model, X_tr)
        pipe.fit(X_tr, y_tr)
        proba = pipe.predict_proba(X_te)[:, 1]
        m = _metrics(y_te, proba)
        m["model"] = name
        m["features"] = "behavioural + customer + merchant (no leaky score)"
        results.append(m)
        curves[name] = (y_te.to_numpy(), proba)
        if name == "random_forest":
            names = pipe.named_steps["pre"].get_feature_names_out()
            imp = pipe.named_steps["clf"].feature_importances_
            importances = dict(
                sorted(zip([n.split("__", 1)[-1] for n in names], imp.round(4).tolist()),
                       key=lambda kv: -kv[1])[:15]
            )

    # Leakage check: the vendor score alone.
    X_tr2, X_te2, y_tr2, y_te2 = _split(df, ["fraud_probability"], seed)
    leak = _pipeline(LogisticRegression(max_iter=1000), X_tr2).fit(X_tr2, y_tr2)
    lp = leak.predict_proba(X_te2)[:, 1]
    m = _metrics(y_te2, lp)
    m["model"] = "leakage_check_fraud_probability_only"
    m["features"] = "fraud_probability only (excluded from real models)"
    results.append(m)
    curves[m["model"]] = (y_te2.to_numpy(), lp)

    return {
        "n_rows": int(len(df)),
        "n_features": len(cols),
        "fraud_rate": round(float(df[TARGET].mean()), 4),
        "test_rows": int(len(y_te)),
        "models": results,
        "feature_importance": importances,
        "_curves": curves,  # not JSON — used by charts, popped before XCom
    }


def _plt():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _saver(out_dir: Path, paths: list[str]):
    plt = _plt()
    out_dir.mkdir(parents=True, exist_ok=True)

    def save(fig, name):
        p = out_dir / name
        fig.tight_layout()
        fig.savefig(p, dpi=120)
        plt.close(fig)
        paths.append(str(p))

    return save


def make_charts(df: pd.DataFrame, out_dir: Path) -> list[str]:
    """EDA charts straight from the warehouse table."""
    plt = _plt()
    paths: list[str] = []
    save = _saver(out_dir, paths)

    # 1. Fraud rate by merchant category
    rate = df.groupby("merchant_category_master")[TARGET].mean().sort_values() * 100
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(rate.index, rate.values, color="#2a6f97")
    ax.axvline(df[TARGET].mean() * 100, color="#c44", ls="--", lw=1, label="overall rate")
    ax.set_xlabel("fraud rate (%)")
    ax.set_title("Fraud rate by merchant category")
    ax.legend()
    save(fig, "fraud_rate_by_category.png")

    # 2. fraud_probability vs label — shows the leakage
    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.linspace(0, 1, 41)
    ax.hist(df.loc[df[TARGET] == 0, "fraud_probability"], bins=bins, alpha=0.7, label="legit", color="#7aa")
    ax.hist(df.loc[df[TARGET] == 1, "fraud_probability"], bins=bins, alpha=0.8, label="fraud", color="#c44")
    ax.set_yscale("log")
    ax.set_xlabel("fraud_probability (upstream score)")
    ax.set_ylabel("transactions (log)")
    ax.set_title("Label is a threshold on fraud_probability → leakage")
    ax.legend()
    save(fig, "leakage_fraud_probability.png")

    # 3. amount distribution by class
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.boxplot([df.loc[df[TARGET] == k, "log_amount"] for k in (0, 1)])
    ax.set_xticks([1, 2], ["legit", "fraud"])
    ax.set_ylabel("log(1 + amount)")
    ax.set_title("Transaction amount by class")
    save(fig, "amount_by_class.png")
    return paths


def model_charts(analysis: dict, out_dir: Path) -> list[str]:
    """Precision-recall curves + feature importance from train_models()."""
    from sklearn.metrics import precision_recall_curve

    plt = _plt()
    paths: list[str] = []
    save = _saver(out_dir, paths)
    if True:

        fig, ax = plt.subplots(figsize=(7, 4))
        for name, (y, p) in (analysis.get("_curves") or {}).items():
            if name == "majority_class_baseline":
                continue
            prec, rec, _ = precision_recall_curve(y, p)
            ax.plot(rec, prec, label=name)
        ax.axhline(analysis["fraud_rate"], color="grey", ls="--", lw=1, label="chance (fraud rate)")
        ax.set_xlabel("recall")
        ax.set_ylabel("precision")
        ax.set_title("Precision–recall on test split")
        ax.legend(fontsize=8)
        save(fig, "precision_recall.png")

        imp = analysis.get("feature_importance") or {}
        if imp:
            fig, ax = plt.subplots(figsize=(7, 4.5))
            items = list(imp.items())[::-1]
            ax.barh([k for k, _ in items], [v for _, v in items], color="#2a6f97")
            ax.set_title("Random forest feature importance (top 15)")
            save(fig, "feature_importance.png")
    return paths


def report_markdown(quality: list[dict], analysis: dict, charts: list[str], run_id: str) -> str:
    lines = [
        f"# Fraud pipeline report — run `{run_id}`",
        "",
        "## Data quality (after cleaning)",
        "",
        "| table | rows | columns | duplicate keys | null cells |",
        "| --- | --- | --- | --- | --- |",
    ]
    for q in quality:
        lines.append(f"| {q['table']} | {q['rows']} | {q['columns']} | {q['duplicate_keys']} | {q['null_cells']} |")
    lines += [
        "",
        f"Merged table: {analysis['n_rows']} rows, {analysis['n_features']} candidate features, "
        f"fraud rate {analysis['fraud_rate']:.2%}.",
        "",
        "## Models (25% stratified test split)",
        "",
        "| model | accuracy | balanced acc | precision | recall | F1 | ROC-AUC | PR-AUC |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for m in analysis["models"]:
        lines.append(
            f"| {m['model']} | {m['accuracy']:.3f} | {m['balanced_accuracy']:.3f} | {m['precision']:.3f} | "
            f"{m['recall']:.3f} | {m['f1']:.3f} | {m['roc_auc']:.3f} | {m['pr_auc']:.3f} |"
        )
    lines += ["", "## Charts", ""] + [f"![{Path(c).stem}]({Path(c).name})" for c in charts]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Local run (no Airflow / no Postgres): python -m pipeline.fraud_etl
# ---------------------------------------------------------------------------
def run_local(data_dir: Path, out_dir: Path) -> dict:
    cust = clean_customers(pd.read_csv(data_dir / "customers.csv"))
    merch = clean_merchants(pd.read_csv(data_dir / "merchants.csv"))
    tx = clean_transactions(pd.read_csv(data_dir / "transactions.csv"))
    q = [
        quality_report(cust, "customers", "customer_id"),
        quality_report(merch, "merchants", "merchant_id"),
        quality_report(tx, "transactions", "transaction_id"),
    ]
    for r in q:
        assert_quality(r)
    merged = merge_all(tx, cust, merch)
    analysis = train_models(merged)
    charts = make_charts(merged, out_dir) + model_charts(analysis, out_dir)
    analysis.pop("_curves", None)
    (out_dir / "report.md").write_text(report_markdown(q, analysis, charts, "local"), encoding="utf-8")
    (out_dir / "metrics.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return analysis


if __name__ == "__main__":
    repo = Path(__file__).resolve().parents[1]
    res = run_local(repo / "datasets" / "airflow", repo / "reports" / "fraud_pipeline_local")
    print(json.dumps(res["models"], indent=2))
