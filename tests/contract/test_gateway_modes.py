"""Gateway live/mock/replay mode contracts (C7/D1)."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GATEWAY_DEFAULT_MODE", "mock")
    monkeypatch.setenv("MOCK_DATASET_SERVICE", "true")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")  # force bus unavailable
    import services.gateway.app.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_mock_session_streams(client):
    res = client.post(
        "/sessions",
        json={"target_column": "churned", "mode": "mock", "scenario": "happy", "mock": True},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["mode"] == "mock"
    assert body["mock"] is True
    sid = body["session_id"]
    with client.stream("GET", f"/sessions/{sid}/events") as stream:
        lines = []
        for line in stream.iter_lines():
            if line:
                lines.append(line)
            if len(lines) > 8:
                break
    assert any("event:" in ln or ln.startswith("data:") for ln in lines)


def test_replay_session_created(client):
    res = client.post(
        "/sessions",
        json={"target_column": "churned", "mode": "replay"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["mode"] == "replay"
    assert body["replay"] is True
    assert body["mock"] is False
    assert body["session_id"].startswith("replay-")


def test_recordings_list(client):
    res = client.get("/recordings")
    assert res.status_code == 200
    assert any(i["id"] == "real_run_churn" for i in res.json()["items"])
