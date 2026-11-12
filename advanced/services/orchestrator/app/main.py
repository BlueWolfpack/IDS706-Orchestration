"""Orchestrator — LangGraph research loop (Stage C6)."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

from contracts import HealthResponse  # noqa: E402
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402
from services.orchestrator.app.graph import GRAPH  # noqa: E402

SERVICE_NAME = "orchestrator"
MOCK = os.getenv("MOCK_ORCHESTRATOR", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="AutoML Orchestrator", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)

_runs: dict[str, dict[str, Any]] = {}


class CreateRunRequest(BaseModel):
    session_id: str | None = None
    dataset_id: str
    target_column: str
    task_type: str = "classification"
    metric: str = "f1"
    target_score: float = 0.75
    experiment_budget: int = 5
    research_strategy: str = "model_search"
    fixed_model_family: str | None = None
    per_trial_timeout_seconds: int = 120


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=MOCK)


@app.post("/runs")
def create_run(body: CreateRunRequest) -> dict[str, Any]:
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    session_id = body.session_id or f"sess-{uuid.uuid4().hex[:8]}"
    thread = {"configurable": {"thread_id": run_id}}
    initial = {
        "session_id": session_id,
        "dataset_id": body.dataset_id,
        "target_column": body.target_column,
        "task_type": body.task_type,
        "metric": body.metric,
        "target_score": body.target_score,
        "experiment_budget": body.experiment_budget,
        "research_strategy": body.research_strategy,
        "fixed_model_family": body.fixed_model_family,
        "per_trial_timeout_seconds": body.per_trial_timeout_seconds,
        "experiment_history": [],
        "experiment_count": 0,
        "retry_count": 0,
        "status": "running",
    }
    # hypothesize↔run is two graph steps per experiment; +profile/finalize +margin.
    recursion_limit = max(50, int(body.experiment_budget) * 3 + 10)
    try:
        final = GRAPH.invoke(
            initial,
            {**thread, "recursion_limit": recursion_limit},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record = {"run_id": run_id, "session_id": session_id, "state": final, "mock": False}
    _runs[run_id] = record
    return record


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    rec = _runs.get(run_id)
    if rec is None:
        # Try checkpointer snapshot
        snap = GRAPH.get_state({"configurable": {"thread_id": run_id}})
        if snap and snap.values:
            return {"run_id": run_id, "state": snap.values, "mock": False}
        raise HTTPException(status_code=404, detail="run not found")
    return rec


@app.post("/runs/{run_id}/pause")
def pause_run(run_id: str) -> dict[str, Any]:
    return {"run_id": run_id, "status": "paused", "note": "cooperative pause placeholder", "mock": False}


@app.post("/runs/{run_id}/resume")
def resume_run(run_id: str) -> dict[str, Any]:
    snap = GRAPH.get_state({"configurable": {"thread_id": run_id}})
    if not snap or not snap.values:
        raise HTTPException(status_code=404, detail="run not found in checkpointer")
    # Resume from last state if interrupted mid-loop
    budget = int((snap.values or {}).get("experiment_budget") or 10)
    recursion_limit = max(50, budget * 3 + 10)
    final = GRAPH.invoke(
        None,
        {"configurable": {"thread_id": run_id}, "recursion_limit": recursion_limit},
    )
    record = {"run_id": run_id, "state": final, "resumed": True, "mock": False}
    _runs[run_id] = record
    return record
