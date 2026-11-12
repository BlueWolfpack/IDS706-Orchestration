"""Tracking-service — MLflow + optional W&B mirroring (Stage C3)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

from contracts import HealthResponse  # noqa: E402
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402
from services.tracking_service.app import store  # noqa: E402

SERVICE_NAME = "tracking_service"
MOCK = os.getenv("MOCK_TRACKING_SERVICE", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="AutoML Tracking Service", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)


class TrackingRunCreate(BaseModel):
    session_id: str
    experiment_id: str
    config: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=MOCK)


@app.post("/runs")
def create_run(body: TrackingRunCreate) -> dict[str, Any]:
    # Never accept or echo API keys.
    safe_tags = {k: v for k, v in body.tags.items() if "key" not in k.lower() and "secret" not in k.lower()}
    try:
        return store.create_run(
            session_id=body.session_id,
            experiment_id=body.experiment_id,
            config=body.config,
            metrics=body.metrics,
            tags=safe_tags,
            idempotency_key=body.idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"tracking backend error: {exc}") from exc


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    rec = store.get_run(run_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="run not found")
    return rec


@app.get("/experiments/{session_id}")
def list_session_experiments(session_id: str) -> dict[str, Any]:
    return {"session_id": session_id, "runs": store.list_session(session_id), "mock": False}
