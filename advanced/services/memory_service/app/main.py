"""Memory-service — four stores, single-writer (Stage C4)."""

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
from services.memory_service.app.store import STORE  # noqa: E402

SERVICE_NAME = "memory_service"
MOCK = os.getenv("MOCK_MEMORY_SERVICE", "false").lower() in {"1", "true", "yes"}

app = FastAPI(title="AutoML Memory Service", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)


class MemoryWrite(BaseModel):
    session_id: str
    writer: str
    content: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=MOCK)


@app.post("/findings")
def post_findings(body: MemoryWrite) -> dict[str, Any]:
    try:
        return STORE.write_findings(body.session_id, body.writer, body.content, body.idempotency_key)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/findings")
def get_findings(session_id: str) -> dict[str, Any]:
    return STORE.get_findings(session_id)


@app.post("/history")
def post_history(body: MemoryWrite) -> dict[str, Any]:
    try:
        return STORE.write_history(body.session_id, body.writer, body.content, body.idempotency_key)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/history")
def get_history(session_id: str) -> dict[str, Any]:
    return STORE.get_history(session_id)


@app.post("/lessons")
def post_lessons(body: MemoryWrite) -> dict[str, Any]:
    try:
        return STORE.write_lesson(body.writer, body.content, body.idempotency_key)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/lessons")
def get_lessons(q: str = "") -> dict[str, Any]:
    return STORE.search_lessons(q)


@app.post("/working/{agent}")
def post_working(agent: str, body: MemoryWrite) -> dict[str, Any]:
    try:
        return STORE.write_working(agent, body.session_id, body.writer, body.content, body.idempotency_key)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/working/{agent}")
def get_working(agent: str, session_id: str) -> dict[str, Any]:
    return STORE.get_working(agent, session_id)
