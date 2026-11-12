"""Agent-service — typed subagents + Composer 2.5 LLM path (Stage C5)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

from contracts import (  # noqa: E402
    AgentInvokeRequest,
    AgentInvokeResponse,
    HealthResponse,
    LeadName,
    SubagentName,
)
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402
from services.agent_service.app.subagents import HANDLERS, query_wandb_readonly  # noqa: E402

SERVICE_NAME = "agent_service"
MOCK = os.getenv("MOCK_AGENT_SERVICE", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="AutoML Agent Service", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=MOCK)


@app.post("/agents/{lead}/{subagent}/invoke", response_model=AgentInvokeResponse)
def invoke_agent(lead: str, subagent: str, body: AgentInvokeRequest) -> AgentInvokeResponse:
    try:
        lead_e = LeadName(lead)
        sub_e = SubagentName(subagent)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"unknown agent {lead}/{subagent}") from exc

    handler = HANDLERS.get(sub_e.value)
    if handler is None:
        raise HTTPException(status_code=404, detail=f"no handler for {subagent}")

    inp = dict(body.input)
    inp.setdefault("session_id", body.session_id)
    inp.setdefault("correlation_id", body.correlation_id)
    try:
        output = handler(inp)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return AgentInvokeResponse(
        session_id=body.session_id,
        lead=lead_e,
        subagent=sub_e,
        output=output,
        mock=False,
    )


@app.post("/tools/query_wandb")
def query_wandb(body: AgentInvokeRequest) -> dict:
    return query_wandb_readonly(body.input)
