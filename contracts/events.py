"""Redis stream / SSE event envelope. Frontend renders only these events."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    SESSION_CREATED = "session_created"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_RESET = "session_reset"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"
    TRIAL_STARTED = "trial_started"
    TRIAL_COMPLETED = "trial_completed"
    TRIAL_FAILED = "trial_failed"
    VERDICT_ISSUED = "verdict_issued"
    BUDGET_UPDATE = "budget_update"
    STOP_REASON = "stop_reason"
    HOLDOUT_EVALUATED = "holdout_evaluated"
    HEALTH = "health"
    WANDB_UNAVAILABLE = "wandb_unavailable"
    SERVICE_ERROR = "service_error"
    ACTIVITY = "activity"


class EventEnvelope(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: str
    correlation_id: str
    source_service: str
    source_agent: str | None = None
    type: EventType
    payload: dict[str, Any] = Field(default_factory=dict)
    # True while any mocked service remains on the path for this run.
    mock: bool = False
