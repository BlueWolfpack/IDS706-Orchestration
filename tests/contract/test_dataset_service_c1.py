"""Stage C1: sealed holdout and real split behavior."""

from __future__ import annotations

import io
from pathlib import Path

import joblib
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "datasets" / "churn_sample.csv"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DATA_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("SERVICE_TOKEN", "dev-service-token")
    monkeypatch.setenv("HARNESS_TOKEN", "dev-service-token")
    # Re-import app so store picks up DATASET_DATA_DIR.
    import importlib

    import services.dataset_service.app.main as main

    importlib.reload(main)
    return TestClient(main.app)


def _headers():
    return {"X-Service-Token": "dev-service-token"}


def test_upload_creates_split_and_profile_has_no_holdout_hint_of_rows(client):
    raw = SAMPLE.read_bytes()
    res = client.post(
        "/datasets",
        headers=_headers(),
        files={"file": ("churn_sample.csv", raw, "text/csv")},
        data={"target_column": "churned", "task_type": "classification"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["mock"] is False
    ds = body["dataset_id"]

    profile = client.get(f"/datasets/{ds}/profile-view", headers=_headers())
    assert profile.status_code == 200
    assert "holdout" not in profile.json().get("note", "").lower() or "sealed" in profile.json()["note"]
    assert profile.json()["n_rows_visible"] < body["n_rows"]

    train = client.get(f"/datasets/{ds}/splits/train", headers=_headers())
    assert train.status_code == 200
    assert train.json()["n_rows"] > 0

    forbidden = client.get(f"/datasets/{ds}/splits/holdout", headers=_headers())
    assert forbidden.status_code == 403


def test_holdout_evaluate_once(client, tmp_path):
    raw = SAMPLE.read_bytes()
    res = client.post(
        "/datasets",
        headers=_headers(),
        files={"file": ("churn_sample.csv", raw, "text/csv")},
        data={"target_column": "churned", "task_type": "classification"},
    )
    ds = res.json()["dataset_id"]
    train = client.get(f"/datasets/{ds}/splits/train", headers=_headers()).json()
    df = pd.DataFrame(train["rows"])
    y = df["churned"]
    X = df.drop(columns=["churned", "customer_id"])
    num_cols = list(X.columns)
    pipe = Pipeline(
        [
            ("pre", ColumnTransformer([("num", StandardScaler(), num_cols)])),
            ("clf", LogisticRegression(max_iter=200, random_state=42)),
        ]
    )
    pipe.fit(X, y)
    model_path = tmp_path / "model.joblib"
    joblib.dump(pipe, model_path)

    first = client.post(
        "/internal/holdout/evaluate",
        headers={**_headers(), "X-Harness-Token": "dev-service-token"},
        json={
            "session_id": "s-test-1",
            "dataset_id": ds,
            "model_ref": str(model_path),
            "metric": "f1",
            "idempotency_key": "holdout-1",
        },
    )
    assert first.status_code == 200, first.text
    assert "score" in first.json()
    assert "rows" not in first.json()

    second = client.post(
        "/internal/holdout/evaluate",
        headers={**_headers(), "X-Harness-Token": "dev-service-token"},
        json={
            "session_id": "s-test-1",
            "dataset_id": ds,
            "model_ref": str(model_path),
            "metric": "f1",
            "idempotency_key": "holdout-2",
        },
    )
    assert second.status_code == 409
