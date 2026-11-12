"""Stage C4: memory stores + single-writer enforcement."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("MOCK_MEMORY_SERVICE", "false")
    import services.memory_service.app.main as main
    import services.memory_service.app.store as store_mod

    store_mod.STORE = store_mod.MemoryStore()
    importlib.reload(main)
    main.STORE = store_mod.STORE
    return TestClient(main.app)


def test_history_readable_and_second_writer_rejected(client):
    a = client.post(
        "/history",
        json={
            "session_id": "s1",
            "writer": "orchestrator",
            "content": {"note": "first"},
            "idempotency_key": "h1",
        },
    )
    assert a.status_code == 200, a.text
    got = client.get("/history", params={"session_id": "s1"})
    assert got.status_code == 200
    assert len(got.json()["items"]) == 1

    b = client.post(
        "/history",
        json={
            "session_id": "s1",
            "writer": "intruder",
            "content": {"note": "nope"},
            "idempotency_key": "h2",
        },
    )
    assert b.status_code == 409


def test_lesson_keyword_search(client):
    client.post(
        "/lessons",
        json={
            "session_id": "s1",
            "writer": "judge",
            "content": {"text": "prefer trees for mild imbalance", "tags": ["trees"]},
            "idempotency_key": "l1",
        },
    )
    res = client.get("/lessons", params={"q": "trees"})
    assert res.status_code == 200
    assert len(res.json()["items"]) >= 1
