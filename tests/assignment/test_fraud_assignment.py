"""Assignment tests — ETL transforms (Part 1) and adapted agent loop (Part 2), no Docker needed.

    python -m pytest tests/assignment -q
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipeline import fraud_etl as etl

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "datasets" / "airflow"


@pytest.fixture(scope="module")
def merged() -> pd.DataFrame:
    cust = etl.clean_customers(pd.read_csv(RAW / "customers.csv"))
    merch = etl.clean_merchants(pd.read_csv(RAW / "merchants.csv"))
    tx = etl.clean_transactions(pd.read_csv(RAW / "transactions.csv"))
    return etl.merge_all(tx, cust, merch)


def test_cleaning_keeps_keys_unique() -> None:
    cust = etl.clean_customers(pd.read_csv(RAW / "customers.csv"))
    rep = etl.quality_report(cust, "customers", "customer_id")
    etl.assert_quality(rep)
    assert cust["loan_status"].isna().sum() == 0


def test_merge_is_one_row_per_transaction(merged: pd.DataFrame) -> None:
    assert len(merged) == len(pd.read_csv(RAW / "transactions.csv"))
    assert merged["transaction_id"].is_unique
    for col in ("customer_tenure_days", "ip_country_mismatch", "merchant_risk_score"):
        assert col in merged.columns


def test_leaky_score_is_not_a_feature(merged: pd.DataFrame) -> None:
    feats = etl.feature_columns(merged)
    assert "fraud_probability" not in feats
    assert etl.TARGET not in feats


def test_create_table_sql_types(merged: pd.DataFrame) -> None:
    sql = etl.create_table_sql(merged.head(), "analytics.t", "transaction_id")
    assert '"amount" DOUBLE PRECISION' in sql and '"timestamp" TIMESTAMP' in sql
    assert 'PRIMARY KEY ("transaction_id")' in sql


def test_leakage_scan_flags_fraud_probability(merged: pd.DataFrame) -> None:
    from lab.langgraph import fraud_tools as ft

    scan = ft.leakage_scan(merged, etl.TARGET)
    assert "fraud_probability" in scan["leaky_columns"]
    assert "transaction_id" in scan["drops"]


def test_agent_loop_end_to_end(tmp_path: Path, merged: pd.DataFrame, monkeypatch) -> None:
    pytest.importorskip("langgraph")
    from lab.langgraph import graph

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("WAREHOUSE_DSN", raising=False)
    monkeypatch.setattr(graph, "REPORTS", tmp_path)
    csv = tmp_path / "fraud.csv"
    merged.to_csv(csv, index=False)

    assert graph.get_status()["ready"]
    res = graph.run_lab_loop(dataset_path=str(csv), target_column="is_fraud", max_cycles=5)
    nodes = [s["node"] for s in res["steps"]]
    assert nodes[:3] == ["warehouse_loader", "data_scientist", "baseline_agent"]
    assert nodes[-1] == "evaluation_reporter"
    assert "context_builder" not in nodes
    assert "fraud_probability" in res["best_spec"]["drop_columns"]
    assert res["holdout_metrics"]["f1"] < 0.99  # leak really removed
    assert (tmp_path / "latest_eval.md").is_file()
