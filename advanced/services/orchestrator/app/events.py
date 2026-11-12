"""Publish live progress events to Redis Streams (same stream the gateway SSE reads)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import redis

from contracts import EventEnvelope, EventType

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_PREFIX = "automl:session:"

_client: redis.Redis | None = None


def _conn() -> redis.Redis | None:
    global _client
    if _client is not None:
        return _client
    try:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
        _client.ping()
        return _client
    except Exception:  # noqa: BLE001
        _client = None
        return None


def stream_key(session_id: str) -> str:
    return f"{STREAM_PREFIX}{session_id}:events"


def emit(
    session_id: str,
    event_type: EventType,
    payload: dict[str, Any],
    *,
    source_service: str = "orchestrator",
    source_agent: str | None = None,
    correlation_id: str | None = None,
) -> str | None:
    event = EventEnvelope(
        timestamp=datetime.now(timezone.utc),
        session_id=session_id,
        correlation_id=correlation_id or str(uuid.uuid4()),
        source_service=source_service,
        source_agent=source_agent,
        type=event_type,
        payload=payload,
        mock=False,
    )
    client = _conn()
    if client is None:
        return None
    try:
        return client.xadd(
            stream_key(session_id),
            {"data": json.dumps(event.model_dump(mode="json"))},
            maxlen=5000,
            approximate=True,
        )
    except Exception:  # noqa: BLE001
        return None
