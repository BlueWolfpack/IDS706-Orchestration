"""Unit tests for merge + subset + baseline prep."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from solution.langgraph.baseline import make_subset, merge_csvs, profile_light, run_prep, train_baseline

REPO = Path(__file__).resolve().parents[2]
LEFT = REPO / "datasets" / "airflow" / "customers.csv"
RIGHT = REPO / "datasets" / "airflow" / "transactions.csv"


pytestmark = pytest.mark.skipif(
    not LEFT.exists() or not RIGHT.exists(),
    reason="datasets/airflow fixtures missing",
)


def test_merge_keeps_fraud_label(tmp_path: Path):
    out = tmp_path / "merged.csv"
    meta = merge_csvs(LEFT, RIGHT, out_csv=out)
    assert meta["n_merged"] == 10000
    df = pd.read_csv(out)
    assert "is_fraud" in df.columns
    assert "credit_score" in df.columns
    assert "amount" in df.columns


def test_make_subset_is_smaller_and_stratified(tmp_path: Path):
    merged = tmp_path / "merged.csv"
    merge_csvs(LEFT, RIGHT, out_csv=merged)
    subset = tmp_path / "subset.csv"
    meta = make_subset(merged, out_csv=subset, n_rows=2000, seed=42)
    assert meta["n_subset"] == 2000
    assert meta["n_source"] == 10000
    df = pd.read_csv(subset)
    assert set(df["is_fraud"].unique()) == {0, 1}
    assert 0.01 < df["is_fraud"].mean() < 0.1


def test_baseline_on_subset(tmp_path: Path):
    merged = tmp_path / "merged.csv"
    merge_csvs(LEFT, RIGHT, out_csv=merged)
    subset = tmp_path / "subset.csv"
    make_subset(merged, out_csv=subset, n_rows=2000, seed=42)
    profile = profile_light(subset)
    result = train_baseline(subset, drop_columns=profile["recommended_drops"], seed=42)
    assert result["holdout_scored"] is False
    assert result["n_train"] > 0


def test_run_prep_publishes_subset():
    result = run_prep(subset_rows=600, run_id="pytest-subset")
    assert result["subset"]["n_subset"] == 600
    assert Path(result["published"]["published_latest"]).is_file()
    assert result["published"]["target_column"] == "is_fraud"
