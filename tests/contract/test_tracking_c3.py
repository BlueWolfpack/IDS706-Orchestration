"""Stage C3: tracking create/list with local MLflow file store."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_TRACKING_SERVICE", "false")
    monkeypatch.setenv("MLFLOW_LOCAL_FALLBACK", "true")
    monkeypatch.setenv("MLFLOW_LOCAL_DIR", str(tmp_path / "mlruns"))
    monkeypatch.setenv("WANDB_ENABLED", "false")
    import services.tracking_service.app.main as main
    import services.tracking_service.app.store as store_mod

    store_mod._idempotency.clear()
    store_mod._runs.clear()
    store_mod._by_session.clear()
    importlib.reload(store_mod)
    importlib.reload(main)
    return TestClient(main.app)


def test_create_and_list_run(client):
    res = client.post(
        "/runs",
        json={
            "session_id": "s1",
            "experiment_id": "e1",
            "config": {"model_family": "logistic_regression"},
            "metrics": {"f1": 0.8},
            "tags": {"phase": "validation"},
            "idempotency_key": "t1",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mock"] is False
    assert body["run_id"]
    listed = client.get("/experiments/s1")
    assert listed.status_code == 200
    assert len(listed.json()["runs"]) == 1
