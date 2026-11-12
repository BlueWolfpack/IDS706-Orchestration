"""Each service OpenAPI must expose the paths listed in contracts.openapi_stubs."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from contracts import HealthResponse
from contracts.openapi_stubs import EXPECTED_PATHS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

SERVICE_MODULES = {
    "gateway": "services.gateway.app.main",
    "orchestrator": "services.orchestrator.app.main",
    "agent_service": "services.agent_service.app.main",
    "harness": "services.harness.app.main",
    "dataset_service": "services.dataset_service.app.main",
    "memory_service": "services.memory_service.app.main",
    "tracking_service": "services.tracking_service.app.main",
}


def _load_app(service: str):
    module = importlib.import_module(SERVICE_MODULES[service])
    return module.app


@pytest.mark.parametrize("service", list(EXPECTED_PATHS.keys()))
def test_expected_paths_present(service: str):
    app = _load_app(service)
    paths = set(app.openapi()["paths"].keys())
    missing = [p for p in EXPECTED_PATHS[service] if p not in paths]
    assert missing == [], f"{service} missing OpenAPI paths: {missing}"


@pytest.mark.parametrize("service", list(SERVICE_MODULES.keys()))
def test_healthz_contract(service: str):
    client = TestClient(_load_app(service))
    response = client.get("/healthz")
    assert response.status_code == 200
    body = HealthResponse.model_validate(response.json())
    assert body.status == "ok"
    assert body.service == service
