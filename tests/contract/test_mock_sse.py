"""Stage A1: mock SSE streams validate against EventEnvelope; every event is mock:true."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from contracts import EventEnvelope, EventType
from mocks.fixtures import SCENARIO_NAMES, load_scenario
from services.gateway.app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _parse_sse_data_lines(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.parametrize("scenario", SCENARIO_NAMES)
def test_fixture_steps_are_valid_event_types(scenario: str):
    steps = load_scenario(scenario)
    assert steps
    for step in steps:
        EventType(step["type"])  # raises if unknown
        assert "source_service" in step


@pytest.mark.parametrize("scenario", ["happy", "revise_loop", "repair", "service_down"])
def test_sse_stream_validates_and_is_mock(client: TestClient, scenario: str):
    created = client.post("/sessions", json={"target_column": "churned", "scenario": scenario})
    assert created.status_code == 201
    body = created.json()
    assert body["mock"] is True
    session_id = body["session_id"]

    with client.stream("GET", f"/sessions/{session_id}/events") as response:
        assert response.status_code == 200
        assert response.headers.get("x-mock-backend") == "true"
        raw = "".join(response.iter_text())

    events = _parse_sse_data_lines(raw)
    assert len(events) >= 3
    for raw_event in events:
        envelope = EventEnvelope.model_validate(raw_event)
        assert envelope.mock is True
        assert envelope.session_id == session_id

    assert events[0]["type"] == EventType.SESSION_CREATED.value
    assert events[-1]["payload"].get("done") is True


def test_pause_and_resume(client: TestClient):
    created = client.post("/sessions", json={"target_column": "churned", "scenario": "happy"})
    session_id = created.json()["session_id"]
    paused = client.post(f"/sessions/{session_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = client.post(f"/sessions/{session_id}/resume")
    assert resumed.json()["status"] == "running"


def test_unknown_scenario_rejected(client: TestClient):
    response = client.post(
        "/sessions",
        json={"target_column": "churned", "scenario": "not_a_real_scenario"},
    )
    assert response.status_code == 400
