"""Stage C2: harness tools, policy, idempotency, real sklearn trials."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "datasets" / "churn_sample.csv"


@pytest.fixture()
def apps(tmp_path, monkeypatch):
    monkeypatch.setenv("DATASET_DATA_DIR", str(tmp_path / "datasets"))
    monkeypatch.setenv("SERVICE_TOKEN", "dev-service-token")
    monkeypatch.setenv("HARNESS_TOKEN", "dev-service-token")
    monkeypatch.setenv("ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("MOCK_HARNESS", "false")

    import importlib

    import services.dataset_service.app.main as ds_main
    import services.harness.app.main as harness_main
    import services.harness.app.tools as tools

    importlib.reload(ds_main)
    importlib.reload(tools)
    importlib.reload(harness_main)

    store = ds_main.store

    def inspect_data(dataset_id: str):
        return store.profile_view(dataset_id)

    def _run_once(session_id, dataset_id, target_column, spec):
        import json
        import uuid

        import joblib
        import pandas as pd

        from services.harness.app.backends import run_trial
        from services.harness.app.policy import POLICY  # noqa: F401

        train = store.read_split(dataset_id, "train")
        validation = store.read_split(dataset_id, "validation")
        profile = store.profile_view(dataset_id)
        drop = list(profile.get("identifier_columns") or [])
        experiment_id = str(spec.get("experiment_id") or f"e-{uuid.uuid4().hex[:8]}")
        pipe, train_metrics, val_metrics, duration = run_trial(
            train=train,
            validation=validation,
            target=target_column,
            model_family=str(spec["model_family"]),
            hyperparameters=dict(spec.get("hyperparameters") or {}),
            drop_columns=drop,
        )
        out_dir = tools.ARTIFACT_ROOT / dataset_id
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / f"{experiment_id}.joblib"
        joblib.dump(pipe, model_path)
        (out_dir / f"{experiment_id}.json").write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "dataset_id": dataset_id,
                    "experiment_id": experiment_id,
                    "spec": spec,
                    "train_metrics": train_metrics,
                    "validation_metrics": val_metrics,
                },
                indent=2,
            )
        )
        return {
            "experiment_id": experiment_id,
            "status": "succeeded",
            "train_metrics": train_metrics,
            "validation_metrics": val_metrics,
            "duration_seconds": duration,
            "artifact_ids": [str(model_path)],
            "model_ref": str(model_path),
            "error": None,
            "mock": False,
        }

    monkeypatch.setattr(tools, "inspect_data", inspect_data)
    monkeypatch.setattr(tools, "_run_once", _run_once)
    tools.ARTIFACT_ROOT = tmp_path / "artifacts"
    harness_main.tools = tools

    return TestClient(harness_main.app), TestClient(ds_main.app)


def _upload(ds_client: TestClient) -> str:
    res = ds_client.post(
        "/datasets",
        headers={"X-Service-Token": "dev-service-token"},
        files={"file": ("churn_sample.csv", SAMPLE.read_bytes(), "text/csv")},
        data={"target_column": "churned", "task_type": "classification"},
    )
    assert res.status_code == 201, res.text
    return res.json()["dataset_id"]


def test_policy_endpoint(apps):
    h, _ = apps
    res = h.get("/policy")
    assert res.status_code == 200
    body = res.json()
    assert body["max_experiments"] == 10
    assert "logistic_regression" in body["allowed_model_families"]
    assert body["mock"] is False


def test_invalid_config_rejected(apps):
    h, ds = apps
    ds_id = _upload(ds)
    res = h.post(
        "/tools/validate_experiment",
        json={
            "session_id": "s1",
            "correlation_id": "c1",
            "experiment_spec": {"model_family": "xgboost", "dataset_id": ds_id},
        },
    )
    assert res.status_code == 200
    assert res.json()["valid"] is False


def test_three_real_experiments_and_idempotency(apps):
    h, ds = apps
    ds_id = _upload(ds)

    specs = [
        {
            "experiment_id": "e-lr",
            "dataset_id": ds_id,
            "target_column": "churned",
            "model_family": "logistic_regression",
            "hyperparameters": {"C": 1.0, "max_iter": 200},
        },
        {
            "experiment_id": "e-rf",
            "dataset_id": ds_id,
            "target_column": "churned",
            "model_family": "random_forest",
            "hyperparameters": {"n_estimators": 30, "max_depth": 4},
        },
        {
            "experiment_id": "e-hgb",
            "dataset_id": ds_id,
            "target_column": "churned",
            "model_family": "hist_gradient_boosting",
            "hyperparameters": {"learning_rate": 0.1, "max_iter": 40},
        },
    ]
    scores = []
    for i, spec in enumerate(specs):
        res = h.post(
            "/tools/run_experiment",
            json={
                "session_id": "s1",
                "correlation_id": f"c-{i}",
                "idempotency_key": f"idem-{i}",
                "experiment_spec": spec,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "succeeded", body
        assert body["mock"] is False
        assert "f1" in body["validation_metrics"]
        scores.append(body["validation_metrics"]["f1"])

        again = h.post(
            "/tools/run_experiment",
            json={
                "session_id": "s1",
                "correlation_id": f"c-{i}",
                "idempotency_key": f"idem-{i}",
                "experiment_spec": spec,
            },
        )
        assert again.json()["validation_metrics"]["f1"] == body["validation_metrics"]["f1"]

    res2 = h.post(
        "/tools/run_experiment",
        json={
            "session_id": "s1",
            "correlation_id": "c-r",
            "idempotency_key": "idem-replay-seed",
            "experiment_spec": {**specs[0], "experiment_id": "e-lr-2"},
        },
    )
    assert abs(res2.json()["validation_metrics"]["f1"] - scores[0]) < 1e-9

    hist = h.get("/tools/get_history", params={"session_id": "s1", "correlation_id": "c"})
    assert hist.status_code == 200
    assert len(hist.json()["items"]) >= 3
