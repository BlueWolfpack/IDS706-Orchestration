"""Harness — seven tools + policy.py (Stage C2). Agents never execute code here."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

from contracts import (  # noqa: E402
    CompareExperimentsRequest,
    GenerateReportRequest,
    GetHistoryRequest,
    HealthResponse,
    InspectDataRequest,
    RunExperimentRequest,
    SaveArtifactRequest,
    ValidateExperimentRequest,
)
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402
from services.harness.app import tools  # noqa: E402
from services.harness.app.policy import get_policy  # noqa: E402

SERVICE_NAME = "harness"
MOCK = os.getenv("MOCK_HARNESS", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="AutoML Harness Service", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=MOCK)


@app.get("/policy")
def policy() -> dict[str, Any]:
    body = get_policy()
    body["mock"] = False
    return body


@app.post("/tools/inspect_data")
def inspect_data(body: InspectDataRequest) -> dict[str, Any]:
    profile = tools.inspect_data(body.dataset_id)
    return {"dataset_id": body.dataset_id, "profile_view": profile, "mock": False}


@app.post("/tools/validate_experiment")
def validate_experiment(body: ValidateExperimentRequest) -> dict[str, Any]:
    return tools.validate_experiment(body.experiment_spec)


@app.post("/tools/run_experiment")
def run_experiment(body: RunExperimentRequest) -> dict[str, Any]:
    spec = dict(body.experiment_spec)
    dataset_id = str(spec.get("dataset_id") or "")
    target_column = str(spec.get("target_column") or "")
    if not dataset_id or not target_column:
        return {
            "experiment_id": str(spec.get("experiment_id") or "e-invalid"),
            "status": "failed",
            "error": "experiment_spec requires dataset_id and target_column",
            "train_metrics": {},
            "validation_metrics": {},
            "duration_seconds": 0.0,
            "artifact_ids": [],
            "mock": False,
        }
    return tools.run_experiment(
        session_id=body.session_id,
        dataset_id=dataset_id,
        target_column=target_column,
        spec=spec,
        idempotency_key=body.idempotency_key,
    )


@app.post("/tools/compare_experiments")
def compare_experiments(body: CompareExperimentsRequest) -> dict[str, Any]:
    return tools.compare_experiments(body.experiment_ids)


@app.get("/tools/get_history")
def get_history(session_id: str, correlation_id: str = "", limit: int = 50) -> dict[str, Any]:
    _ = GetHistoryRequest(session_id=session_id, correlation_id=correlation_id or "x", limit=limit)
    return tools.get_history(session_id, limit=limit)


@app.post("/tools/save_artifact")
def save_artifact(body: SaveArtifactRequest) -> dict[str, Any]:
    return tools.save_artifact(
        name=body.name,
        artifact_type=body.artifact_type,
        metadata=body.metadata,
        idempotency_key=body.idempotency_key,
    )


@app.post("/tools/generate_report")
def generate_report(body: GenerateReportRequest) -> dict[str, Any]:
    return tools.generate_report(body.session_id, body.idempotency_key)
