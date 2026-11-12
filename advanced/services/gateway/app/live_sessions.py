"""Live gateway sessions: kick off orchestrator; SSE fans in Redis Streams in real time."""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

import httpx

from contracts import EventEnvelope, EventType
from services.gateway.app.redis_bus import bus

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8001")
DATASET_SERVICE_URL = os.getenv("DATASET_SERVICE_URL", "http://dataset_service:8004")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")
BUNDLED_CSV = Path(os.getenv("BUNDLED_CSV", "/bundled/churn_sample.csv"))
if not BUNDLED_CSV.exists():
    BUNDLED_CSV = Path(__file__).resolve().parents[3] / "datasets" / "churn_sample.csv"
DATASETS_DIR = Path(os.getenv("DATASETS_DIR", str(BUNDLED_CSV.parent)))
if not DATASETS_DIR.exists():
    DATASETS_DIR = Path(__file__).resolve().parents[3] / "datasets"


@dataclass
class LiveSession:
    session_id: str
    correlation_id: str
    dataset_id: str | None = None
    target_column: str = "churned"
    task_type: str = "classification"
    metric: str = "f1"
    target_score: float = 0.7
    experiment_budget: int = 5
    research_strategy: str = "model_search"
    fixed_model_family: str | None = None
    per_trial_timeout_seconds: int = 120
    status: str = "created"
    run_id: str | None = None
    final_state: dict[str, Any] | None = None
    project_id: str | None = None
    dataset_filename: str | None = None
    history: list[EventEnvelope] = field(default_factory=list)
    _subscribers: list[asyncio.Queue[EventEnvelope | None]] = field(default_factory=list)
    _task: asyncio.Task | None = None
    _done: bool = False
    # False for sessions reattached after gateway restart — do not auto-kick orchestrator.
    _allow_autostart: bool = True


class LiveSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, LiveSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        correlation_id: str,
        *,
        target_column: str = "churned",
        task_type: str = "classification",
        metric: str = "f1",
        target_score: float = 0.7,
        experiment_budget: int = 5,
        auto_upload: bool = True,
        project_id: str | None = None,
        dataset_filename: str | None = None,
        research_strategy: str = "model_search",
        fixed_model_family: str | None = None,
        per_trial_timeout_seconds: int = 120,
    ) -> LiveSession:
        sid = f"sess-{uuid.uuid4().hex[:10]}"
        session = LiveSession(
            session_id=sid,
            correlation_id=correlation_id,
            target_column=target_column,
            task_type=task_type,
            metric=metric,
            target_score=target_score,
            experiment_budget=experiment_budget,
            research_strategy=research_strategy,
            fixed_model_family=fixed_model_family,
            per_trial_timeout_seconds=per_trial_timeout_seconds,
            project_id=project_id,
            dataset_filename=dataset_filename
            or ("churn_sample.csv" if auto_upload else None),
        )
        async with self._lock:
            self._sessions[sid] = session
        await self.emit(
            session,
            EventType.SESSION_CREATED,
            {"message": "live session created", "mode": "live"},
        )
        if auto_upload:
            await self.attach_bundled_dataset(session)
        return session

    def get(self, session_id: str) -> LiveSession | None:
        return self._sessions.get(session_id)

    def revive(
        self,
        session_id: str,
        *,
        status: str = "completed",
        target_column: str = "churned",
        task_type: str = "classification",
        metric: str = "f1",
        target_score: float = 0.7,
        experiment_budget: int = 5,
        research_strategy: str = "model_search",
        fixed_model_family: str | None = None,
        per_trial_timeout_seconds: int = 120,
        project_id: str | None = None,
        dataset_id: str | None = None,
        dataset_filename: str | None = None,
        correlation_id: str | None = None,
    ) -> LiveSession:
        """Reattach a session after gateway restart so Redis history can be replayed."""
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        done = status in {"completed", "failed", "reset", "paused"}
        session = LiveSession(
            session_id=session_id,
            correlation_id=correlation_id or session_id,
            dataset_id=dataset_id,
            target_column=target_column,
            task_type=task_type,
            metric=metric,
            target_score=target_score,
            experiment_budget=experiment_budget,
            research_strategy=research_strategy,
            fixed_model_family=fixed_model_family,
            per_trial_timeout_seconds=per_trial_timeout_seconds,
            status=status,
            project_id=project_id,
            dataset_filename=dataset_filename,
            _done=done,
            _allow_autostart=False,
        )
        self._sessions[session_id] = session
        return session

    def resolve_catalog_path(self, filename: str) -> Path:
        """Resolve a safe path under DATASETS_DIR (no path traversal)."""
        name = Path(filename).name
        if not name.lower().endswith(".csv"):
            raise FileNotFoundError(f"not a csv: {filename}")
        path = (DATASETS_DIR / name).resolve()
        root = DATASETS_DIR.resolve()
        if not str(path).startswith(str(root)) or not path.is_file():
            raise FileNotFoundError(f"dataset not in catalog: {name}")
        return path

    def list_catalog(self) -> list[dict[str, Any]]:
        if not DATASETS_DIR.exists():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(DATASETS_DIR.glob("*.csv")):
            items.append(
                {
                    "filename": path.name,
                    "bytes": path.stat().st_size,
                    "source": "catalog",
                }
            )
        return items

    def save_to_catalog(self, filename: str, content: bytes) -> Path:
        """Persist an uploaded CSV under DATASETS_DIR so it can be reused later."""
        name = Path(filename).name
        if not name.lower().endswith(".csv"):
            name = f"{name}.csv"
        DATASETS_DIR.mkdir(parents=True, exist_ok=True)
        path = DATASETS_DIR / name
        path.write_bytes(content)
        return path

    async def attach_bundled_dataset(self, session: LiveSession) -> str:
        return await self.attach_dataset_file(session, BUNDLED_CSV)

    async def attach_dataset_file(self, session: LiveSession, path: Path) -> str:
        if not path.exists():
            raise FileNotFoundError(f"CSV missing: {path}")
        content = path.read_bytes()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{DATASET_SERVICE_URL}/datasets",
                headers={"X-Service-Token": SERVICE_TOKEN},
                files={"file": (path.name, content, "text/csv")},
                data={
                    "target_column": session.target_column,
                    "task_type": session.task_type,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        session.dataset_id = body["dataset_id"]
        session.dataset_filename = path.name
        await self.emit(
            session,
            EventType.ACTIVITY,
            {
                "message": "dataset uploaded",
                "dataset_id": session.dataset_id,
                "filename": path.name,
            },
            source_service="dataset_service",
        )
        return session.dataset_id

    async def emit(
        self,
        session: LiveSession,
        event_type: EventType,
        payload: dict[str, Any],
        source_agent: str | None = None,
        source_service: str = "gateway",
    ) -> EventEnvelope:
        event = EventEnvelope(
            timestamp=datetime.now(timezone.utc),
            session_id=session.session_id,
            correlation_id=session.correlation_id,
            source_service=source_service,
            source_agent=source_agent,
            type=event_type,
            payload=payload,
            mock=False,
        )
        session.history.append(event)
        await bus.publish(session.session_id, event)
        for q in list(session._subscribers):
            await q.put(event)
        return event

    async def start_run(self, session: LiveSession) -> None:
        if not session.dataset_id:
            raise ValueError("upload a dataset before starting")
        if session._task and not session._task.done():
            return

        async def _runner() -> None:
            from services.gateway.app.project_store import project_store

            session.status = "running"
            if session.project_id:
                project_store.update_session(session.session_id, status="running")
            await self.emit(
                session,
                EventType.ACTIVITY,
                {"message": "orchestrator run starting"},
                source_service="orchestrator",
            )
            try:
                # Orchestrator publishes agent/trial events to Redis while this awaits.
                async with httpx.AsyncClient(timeout=600.0) as client:
                    resp = await client.post(
                        f"{ORCHESTRATOR_URL}/runs",
                        headers={"X-Service-Token": SERVICE_TOKEN},
                        json={
                            "session_id": session.session_id,
                            "dataset_id": session.dataset_id,
                            "target_column": session.target_column,
                            "task_type": session.task_type,
                            "metric": session.metric,
                            "experiment_budget": session.experiment_budget,
                            "target_score": session.target_score,
                            "research_strategy": session.research_strategy,
                            "fixed_model_family": session.fixed_model_family,
                            "per_trial_timeout_seconds": session.per_trial_timeout_seconds,
                        },
                    )
                    resp.raise_for_status()
                    body = resp.json()
                session.run_id = body.get("run_id")
                session.final_state = body.get("state") or {}
                session.status = "completed"
                state = session.final_state or {}
                if session.project_id:
                    project_store.update_session(
                        session.session_id,
                        status="completed",
                        best_val_score=state.get("best_val_score"),
                        holdout_score=state.get("holdout_score"),
                        stop_reason=state.get("stop_reason") or state.get("status"),
                        experiments_used=state.get("experiment_count"),
                        dataset_id=session.dataset_id,
                        dataset_filename=session.dataset_filename,
                    )
                # STOP_REASON is emitted by orchestrator finalize; ensure terminal signal.
                if not any(e.type == EventType.STOP_REASON for e in session.history):
                    await self.emit(
                        session,
                        EventType.STOP_REASON,
                        {
                            "stop_reason": state.get("stop_reason") or state.get("status"),
                            "best_experiment_id": state.get("best_experiment_id"),
                            "best_val_score": state.get("best_val_score"),
                            "holdout_score": state.get("holdout_score"),
                        },
                        source_service="orchestrator",
                    )
            except Exception as exc:  # noqa: BLE001
                session.status = "failed"
                if session.project_id:
                    project_store.update_session(
                        session.session_id,
                        status="failed",
                        stop_reason=str(exc),
                        dataset_id=session.dataset_id,
                        dataset_filename=session.dataset_filename,
                    )
                await self.emit(
                    session,
                    EventType.SERVICE_ERROR,
                    {"error": str(exc)},
                    source_service="orchestrator",
                )
            finally:
                session._done = True
                for q in list(session._subscribers):
                    await q.put(None)

        session._task = asyncio.create_task(_runner())

    async def emit_service_health(self, session: LiveSession) -> None:
        from services.gateway.app.service_health import probe_payload

        payload = await probe_payload()
        await self.emit(session, EventType.HEALTH, payload, source_service="gateway")

    async def subscribe(
        self, session: LiveSession, last_id: str = "0-0"
    ) -> AsyncIterator[tuple[str | None, EventEnvelope]]:
        """Yield (redis_id|None, event). Prefers Redis Streams for live fan-in."""
        # Fresh probe so the Control Center strip is not stuck on "unknown".
        try:
            await self.emit_service_health(session)
        except Exception:  # noqa: BLE001
            await self.emit(
                session,
                EventType.HEALTH,
                {
                    "services": {name: "unknown" for name in (
                        "gateway",
                        "orchestrator",
                        "agent_service",
                        "harness",
                        "dataset_service",
                        "memory_service",
                        "tracking_service",
                    )},
                    "note": "health probe failed",
                },
                source_service="gateway",
            )
        if (
            session._allow_autostart
            and session.dataset_id
            and session.status == "created"
        ):
            await self.start_run(session)

        # Redis-first path: orchestrator + gateway both XADD here.
        if await bus.connect():
            cursor = last_id
            idle_after_done = 0
            while True:
                batch = await bus.xread_once(
                    session.session_id,
                    cursor,
                    block_ms=800 if session._done else 1500,
                    count=200 if session._done else 50,
                )
                if not batch:
                    if session._done:
                        idle_after_done += 1
                        # Drain once more, then stop.
                        if idle_after_done >= 2:
                            break
                    continue
                idle_after_done = 0
                for msg_id, event in batch:
                    cursor = msg_id
                    yield msg_id, event
                    if event.type in {EventType.STOP_REASON, EventType.SERVICE_ERROR}:
                        # Keep reading briefly so finalize trails arrive, then allow idle exit.
                        idle_after_done = 0
            return

        # Fallback: in-memory subscriber queue if Redis is down.
        queue: asyncio.Queue[EventEnvelope | None] = asyncio.Queue()
        session._subscribers.append(queue)
        try:
            for past in list(session.history):
                yield None, past
            if session._done:
                return
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield None, item
        finally:
            if queue in session._subscribers:
                session._subscribers.remove(queue)


live_store = LiveSessionStore()
