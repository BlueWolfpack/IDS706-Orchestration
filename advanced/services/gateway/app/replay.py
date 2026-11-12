"""Replay a recorded *real* run JSON through the same SSE contract (Stage D1)."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from contracts import EventEnvelope, EventType

ROOT = Path(__file__).resolve().parents[3]
RECORDINGS = ROOT / "mocks" / "recordings"
DEFAULT_RECORDING = RECORDINGS / "real_run_churn.json"


@dataclass
class ReplaySession:
    session_id: str
    correlation_id: str
    recording_path: Path
    status: str = "created"
    history: list[EventEnvelope] = field(default_factory=list)
    _subscribers: list[asyncio.Queue[EventEnvelope | None]] = field(default_factory=list)
    _task: asyncio.Task | None = None


class ReplayStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ReplaySession] = {}

    async def create(self, correlation_id: str, recording: str | None = None) -> ReplaySession:
        path = RECORDINGS / recording if recording else DEFAULT_RECORDING
        if not path.exists():
            path = DEFAULT_RECORDING
        sid = f"replay-{uuid.uuid4().hex[:10]}"
        session = ReplaySession(
            session_id=sid, correlation_id=correlation_id, recording_path=path
        )
        self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> ReplaySession | None:
        return self._sessions.get(session_id)

    async def subscribe(self, session: ReplaySession) -> AsyncIterator[EventEnvelope]:
        queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue()
        session._subscribers.append(queue)

        async def _play() -> None:
            session.status = "running"
            raw = json.loads(session.recording_path.read_text())
            events = raw.get("events") or []
            # Announce replay (not live, not mock).
            intro = EventEnvelope(
                timestamp=datetime.now(timezone.utc),
                session_id=session.session_id,
                correlation_id=session.correlation_id,
                source_service="gateway",
                type=EventType.SESSION_CREATED,
                payload={
                    "message": "Replay of a recorded real run",
                    "mode": "replay",
                    "recording": session.recording_path.name,
                    "recorded_at": raw.get("recorded_at"),
                },
                mock=False,
            )
            session.history.append(intro)
            await queue.put(intro)
            for step in events:
                delay = float(step.get("delay_seconds") or 0.4)
                await asyncio.sleep(min(delay, 2.0))
                et = step.get("type") or "activity"
                try:
                    event_type = EventType(et)
                except ValueError:
                    event_type = EventType.ACTIVITY
                event = EventEnvelope(
                    timestamp=datetime.now(timezone.utc),
                    session_id=session.session_id,
                    correlation_id=session.correlation_id,
                    source_service=str(step.get("source_service") or "gateway"),
                    source_agent=step.get("source_agent"),
                    type=event_type,
                    payload=dict(step.get("payload") or {}),
                    mock=False,
                )
                # Tag every payload so UI can show replay banner.
                event.payload.setdefault("mode", "replay")
                session.history.append(event)
                await queue.put(event)
            session.status = "completed"
            await queue.put(None)

        session._task = asyncio.create_task(_play())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            if queue in session._subscribers:
                session._subscribers.remove(queue)


replay_store = ReplayStore()


def list_recordings() -> list[dict[str, Any]]:
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(RECORDINGS.glob("*.json")):
        try:
            meta = json.loads(p.read_text())
            out.append(
                {
                    "id": p.stem,
                    "file": p.name,
                    "recorded_at": meta.get("recorded_at"),
                    "note": meta.get("note"),
                }
            )
        except Exception:  # noqa: BLE001
            out.append({"id": p.stem, "file": p.name})
    return out
