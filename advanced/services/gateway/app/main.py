"""Gateway — mock SSE, live Redis-backed SSE, or recorded real-run replay."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in here.parents:
        if (candidate / "contracts").is_dir():
            return candidate
    return here.parents[3]


ROOT = _repo_root()
sys.path.insert(0, str(ROOT))
_services = ROOT / "advanced" / "services"
if not _services.is_dir():
    _services = ROOT / "services"
sys.path.insert(0, str(_services))

from contracts import (  # noqa: E402
    CreateProjectRequest,
    CreateSessionRequest,
    CreateSessionResponse,
    EventType,
    HealthResponse,
    PriorDataset,
    ProjectDetail,
    ProjectSummary,
    SessionCommandResponse,
    TrainingSessionRecord,
)
from mocks.fixtures import SCENARIO_NAMES  # noqa: E402
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402

from services.gateway.app.mock_sessions import store  # noqa: E402
from services.gateway.app import mock_sessions as mock_mod  # noqa: E402
from services.gateway.app.live_sessions import live_store  # noqa: E402
from services.gateway.app.project_store import project_store  # noqa: E402
from services.gateway.app.replay import list_recordings, replay_store  # noqa: E402
from services.gateway.app.redis_bus import bus, bus_status  # noqa: E402
from services.gateway.app.loop_runs import loop_run_store  # noqa: E402

SERVICE_NAME = "gateway"
# Env default for health; per-session mode comes from CreateSessionRequest.
DEFAULT_MODE = os.getenv("GATEWAY_DEFAULT_MODE", "live")
MOCK_DATASET_SERVICE = os.getenv("MOCK_DATASET_SERVICE", "false").lower() in {"1", "true", "yes"}
DATASET_SERVICE_URL = os.getenv("DATASET_SERVICE_URL", "http://dataset_service:8004")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")

app = FastAPI(title="AutoML Gateway", version="0.3.0")
app.add_middleware(CorrelationIdMiddleware)

# session_id -> mode
_session_modes: dict[str, str] = {}


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


def _resolve_mode(body: CreateSessionRequest) -> str:
    # Explicit mode wins. Legacy: mock=true or a fixture scenario name ⇒ mock.
    if body.mock:
        return "mock"
    if body.mode and body.mode != "live":
        return body.mode
    if body.scenario:
        return "mock"
    if body.mode == "live":
        return "live"
    return DEFAULT_MODE


@app.on_event("startup")
async def _startup() -> None:
    await bus.connect()


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    redis_ok = await bus.connect()
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        mock=False,
        details={
            "default_mode": DEFAULT_MODE,
            "scenarios": list(SCENARIO_NAMES),
            "redis": {**bus_status(), "connected": redis_ok},
            "recordings": list_recordings(),
        },
    )


@app.get("/services/health")
async def services_health() -> dict:
    """Aggregate /healthz probes for the Control Center strip (and debugging)."""
    from services.gateway.app.service_health import probe_payload

    return await probe_payload()


@app.get("/recordings")
def recordings() -> dict:
    return {"items": list_recordings()}


def _register_training_session(
    *,
    session_id: str,
    body: CreateSessionRequest,
    mode: str,
    mock: bool,
    replay: bool,
    dataset_filename: str | None = None,
    dataset_id: str | None = None,
    status: str = "created",
) -> str | None:
    """Attach session to a project when project_id is provided. Returns project_id."""
    project_id = body.project_id
    if not project_id:
        return None
    if not project_store.ensure_project(project_id):
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    project_store.register_session(
        session_id=session_id,
        project_id=project_id,
        target_column=body.target_column,
        mode=mode,  # type: ignore[arg-type]
        mock=mock,
        replay=replay,
        task_type=body.task_type,
        metric=body.metric,
        target_score=body.target_score,
        experiment_budget=body.experiment_budget,
        dataset_filename=dataset_filename or body.dataset_filename,
        dataset_id=dataset_id,
        status=status,
        research_strategy=body.research_strategy,
        fixed_model_family=body.fixed_model_family,
        per_trial_timeout_seconds=body.per_trial_timeout_seconds,
    )
    return project_id


@app.get("/projects", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return project_store.list_projects()


@app.post("/projects", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(body: CreateProjectRequest) -> ProjectSummary:
    return project_store.create_project(name=body.name, description=body.description)


@app.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    detail = project_store.get_project(project_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    return detail


@app.get("/projects/{project_id}/prior-datasets", response_model=list[PriorDataset])
def list_prior_datasets(project_id: str) -> list[PriorDataset]:
    """CSVs previously used on this project, plus any files in the datasets catalog."""
    if not project_store.ensure_project(project_id):
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    history = {d.filename: d for d in project_store.prior_datasets(project_id)}
    for item in live_store.list_catalog():
        name = item["filename"]
        if name in history:
            continue
        history[name] = PriorDataset(
            filename=name,
            times_used=0,
            last_used_at=None,
            source="catalog",
        )
    from datetime import datetime, timezone

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(
        history.values(),
        key=lambda d: (d.last_used_at or epoch, d.filename),
        reverse=True,
    )


@app.get("/sessions/{session_id}/record", response_model=TrainingSessionRecord)
def get_session_record(session_id: str) -> TrainingSessionRecord:
    rec = project_store.get_session(session_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session record {session_id} not found")
    return rec


class SessionRecordPatch(BaseModel):
    status: str | None = None
    best_val_score: float | None = None
    holdout_score: float | None = None
    stop_reason: str | None = None
    experiments_used: int | None = None


@app.patch("/sessions/{session_id}/record", response_model=TrainingSessionRecord)
def patch_session_record(session_id: str, body: SessionRecordPatch) -> TrainingSessionRecord:
    """UI/gateway sync for mock/replay completion and live metric refresh."""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    rec = project_store.update_session(session_id, **fields)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"session record {session_id} not found")
    return rec


@app.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSessionRequest, request: Request) -> CreateSessionResponse:
    mode = _resolve_mode(body)
    cid = _correlation_id(request)

    if mode == "mock":
        scenario = body.scenario or "happy"
        if scenario not in SCENARIO_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"unknown scenario {scenario!r}; choose one of {list(SCENARIO_NAMES)}",
            )
        session = await store.create(scenario=scenario, correlation_id=cid)
        _session_modes[session.session_id] = "mock"
        project_id = _register_training_session(
            session_id=session.session_id,
            body=body,
            mode="mock",
            mock=True,
            replay=False,
            dataset_filename=body.dataset_filename or "mock-fixture",
            status="running",
        )
        return CreateSessionResponse(
            session_id=session.session_id,
            status="created",
            mock=True,
            mode="mock",
            replay=False,
            project_id=project_id,
        )

    if mode == "replay":
        session = await replay_store.create(correlation_id=cid, recording=body.recording)
        _session_modes[session.session_id] = "replay"
        project_id = _register_training_session(
            session_id=session.session_id,
            body=body,
            mode="replay",
            mock=False,
            replay=True,
            dataset_filename=body.dataset_filename or body.recording or "replay",
            status="running",
        )
        return CreateSessionResponse(
            session_id=session.session_id,
            status="created",
            mock=False,
            mode="replay",
            replay=True,
            project_id=project_id,
        )

    # live
    reuse_name = (body.reuse_dataset_filename or "").strip() or None
    auto_upload = bool(body.use_sample_dataset) and not reuse_name
    try:
        session = await live_store.create(
            correlation_id=cid,
            target_column=body.target_column,
            task_type=body.task_type,
            metric=body.metric,
            target_score=body.target_score,
            experiment_budget=body.experiment_budget,
            auto_upload=auto_upload,
            project_id=body.project_id,
            dataset_filename=body.dataset_filename or reuse_name,
            research_strategy=body.research_strategy,
            fixed_model_family=body.fixed_model_family,
            per_trial_timeout_seconds=body.per_trial_timeout_seconds,
        )
        if reuse_name:
            path = live_store.resolve_catalog_path(reuse_name)
            await live_store.attach_dataset_file(session, path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"live session setup failed: {exc}") from exc
    _session_modes[session.session_id] = "live"
    project_id = _register_training_session(
        session_id=session.session_id,
        body=body,
        mode="live",
        mock=False,
        replay=False,
        dataset_filename=session.dataset_filename or body.dataset_filename or reuse_name,
        dataset_id=session.dataset_id,
        status="created",
    )
    return CreateSessionResponse(
        session_id=session.session_id,
        status="created",
        mock=False,
        mode="live",
        replay=False,
        project_id=project_id,
    )


@app.post("/sessions/{session_id}/pause", response_model=SessionCommandResponse)
async def pause_session(session_id: str) -> SessionCommandResponse:
    mode = _session_modes.get(session_id, "live")
    if mode == "mock":
        try:
            session = await store.pause(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found") from None
        return SessionCommandResponse(
            session_id=session.session_id,
            status=session.status.value,
            message="paused at next fixture step",
            mock=True,
            mode="mock",
        )
    if mode == "replay":
        return SessionCommandResponse(
            session_id=session_id, status="paused", message="replay pause is cooperative only", mode="replay"
        )
    session = live_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    session.status = "paused"
    return SessionCommandResponse(
        session_id=session_id, status="paused", message="pause acknowledged", mode="live"
    )


@app.post("/sessions/{session_id}/resume", response_model=SessionCommandResponse)
async def resume_session(session_id: str) -> SessionCommandResponse:
    mode = _session_modes.get(session_id, "live")
    if mode == "mock":
        try:
            session = await store.resume(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found") from None
        return SessionCommandResponse(
            session_id=session.session_id,
            status=session.status.value,
            message="resumed",
            mock=True,
            mode="mock",
        )
    if mode == "replay":
        return SessionCommandResponse(
            session_id=session_id, status="running", message="replay continues", mode="replay"
        )
    session = live_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    if session.dataset_id:
        await live_store.start_run(session)
    return SessionCommandResponse(
        session_id=session_id, status=session.status, message="resumed", mode="live"
    )


@app.post("/sessions/{session_id}/reset", response_model=SessionCommandResponse)
async def reset_session(session_id: str) -> SessionCommandResponse:
    mode = _session_modes.get(session_id, "live")
    if mode == "mock":
        try:
            session = await store.reset(session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found") from None
        return SessionCommandResponse(
            session_id=session.session_id,
            status=session.status.value,
            message="reset — SSE stream cancelled",
            mock=True,
            mode="mock",
        )
    if mode == "replay":
        return SessionCommandResponse(
            session_id=session_id, status="reset", message="replay reset", mode="replay"
        )
    session = live_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    session.status = "reset"
    session.final_state = None
    return SessionCommandResponse(
        session_id=session_id, status="reset", message="reset", mode="live"
    )


async def _revive_live_session(session_id: str):
    """Rebuild an in-memory live session from the project registry and/or Redis stream."""
    existing = live_store.get(session_id)
    if existing is not None:
        return existing
    rec = project_store.get_session(session_id)
    has_stream = await bus.stream_exists(session_id)
    if rec is None and not has_stream:
        return None
    if rec is not None and rec.mode not in (None, "live"):
        # Mock/replay sessions are handled by their own stores.
        if not has_stream:
            return None
    return live_store.revive(
        session_id,
        status=(rec.status if rec else "completed"),
        target_column=(rec.target_column if rec else "churned"),
        task_type=(rec.task_type if rec else "classification"),
        metric=(rec.metric if rec else "f1"),
        target_score=(rec.target_score if rec else 0.7),
        experiment_budget=(rec.experiment_budget if rec else 5),
        research_strategy=(rec.research_strategy if rec else "model_search"),
        fixed_model_family=(rec.fixed_model_family if rec else None),
        per_trial_timeout_seconds=(rec.per_trial_timeout_seconds if rec else 120),
        project_id=(rec.project_id if rec else None),
        dataset_id=(rec.dataset_id if rec else None),
        dataset_filename=(rec.dataset_filename if rec else None),
    )


@app.get("/sessions/{session_id}/events")
async def session_events(
    session_id: str,
    request: Request,
    scenario: str | None = Query(default=None),
) -> StreamingResponse:
    mode = _session_modes.get(session_id)
    if mode is None:
        # Infer from stores for resilience after restart (replay/live ids are prefixed).
        if store.get(session_id) is not None:
            mode = "mock"
        elif replay_store.get(session_id) is not None:
            mode = "replay"
        elif live_store.get(session_id) is not None:
            mode = "live"
        elif await _revive_live_session(session_id) is not None:
            mode = "live"
            _session_modes[session_id] = "live"
        else:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    if mode == "mock":
        session = store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")
        _ = scenario

        async def mock_stream():
            async for event in mock_mod.replay_scenario(session):
                payload = event.model_dump(mode="json")
                yield ": mock fixture event\n"
                yield f"event: {event.type.value}\n"
                yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            mock_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Mock-Backend": "true",
                "X-Session-Mode": "mock",
                "X-Accel-Buffering": "no",
            },
        )

    if mode == "replay":
        session = replay_store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")

        async def replay_stream():
            async for event in replay_store.subscribe(session):
                payload = event.model_dump(mode="json")
                yield ": replay of a recorded real run\n"
                yield f"event: {event.type.value}\n"
                yield f"data: {json.dumps(payload)}\n\n"

        return StreamingResponse(
            replay_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Mock-Backend": "false",
                "X-Session-Mode": "replay",
                "X-Accel-Buffering": "no",
            },
        )

    session = live_store.get(session_id) or await _revive_live_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")
    _session_modes[session_id] = "live"

    last_event_id = request.headers.get("Last-Event-ID") or "0-0"

    async def live_stream():
        # Push a health snapshot first so the strip updates even if Redis
        # cursor / reconnect skips the probe published inside subscribe().
        try:
            from datetime import datetime, timezone

            from services.gateway.app.service_health import probe_payload

            health_payload = await probe_payload()
            health_event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "correlation_id": session.correlation_id,
                "source_service": "gateway",
                "source_agent": None,
                "type": EventType.HEALTH.value,
                "payload": health_payload,
                "mock": False,
            }
            yield f"event: {EventType.HEALTH.value}\n"
            yield f"data: {json.dumps(health_event)}\n\n"
        except Exception:  # noqa: BLE001
            pass
        async for msg_id, event in live_store.subscribe(session, last_id=last_event_id):
            payload = event.model_dump(mode="json")
            if msg_id:
                yield f"id: {msg_id}\n"
            yield f"event: {event.type.value}\n"
            yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        live_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Mock-Backend": "false",
            "X-Session-Mode": "live",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/sessions/{session_id}/datasets")
async def upload_dataset(
    session_id: str,
    file: UploadFile | None = File(default=None),
    target_column: str = Form(default="churned"),
    task_type: str = Form(default="classification"),
) -> JSONResponse:
    mode = _session_modes.get(session_id, "live")
    if mode == "mock":
        if store.get(session_id) is None:
            raise HTTPException(status_code=404, detail=f"session {session_id} not found")
        if MOCK_DATASET_SERVICE:
            filename = file.filename if file else "churn_sample.csv"
            return JSONResponse(
                {
                    "session_id": session_id,
                    "dataset_id": f"ds-mock-{session_id[-8:]}",
                    "filename": filename,
                    "mock": True,
                    "note": "SAMPLE: upload accepted in mock mode",
                }
            )

    if mode == "replay":
        return JSONResponse(
            {
                "session_id": session_id,
                "dataset_id": "ds-recorded",
                "mock": False,
                "mode": "replay",
                "note": "Replay uses the recorded dataset id; upload ignored",
            }
        )

    live = live_store.get(session_id)
    if live is None and mode == "live":
        raise HTTPException(status_code=404, detail=f"session {session_id} not found")

    if MOCK_DATASET_SERVICE:
        filename = file.filename if file else "churn_sample.csv"
        return JSONResponse(
            {
                "session_id": session_id,
                "dataset_id": f"ds-mock-{session_id[-8:]}",
                "filename": filename,
                "mock": True,
            }
        )

    import httpx

    if file is None:
        raise HTTPException(status_code=400, detail="file required")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        live_store.save_to_catalog(file.filename or "upload.csv", content)
    except OSError:
        pass
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(
            f"{DATASET_SERVICE_URL}/datasets",
            headers={"X-Service-Token": SERVICE_TOKEN, "X-Correlation-Id": session_id},
            files={"file": (file.filename or "upload.csv", content, file.content_type or "text/csv")},
            data={"target_column": target_column, "task_type": task_type},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    body = resp.json()
    body["session_id"] = session_id
    if live is not None:
        live.dataset_id = body["dataset_id"]
        live.target_column = body.get("target_column") or target_column
        live.task_type = task_type
        live.dataset_filename = file.filename or "upload.csv"
        if live.project_id:
            project_store.update_session(
                live.session_id,
                dataset_id=live.dataset_id,
                dataset_filename=live.dataset_filename,
                target_column=live.target_column,
            )
        await live_store.emit(
            live,
            EventType.ACTIVITY,
            {
                "message": "dataset uploaded",
                "dataset_id": live.dataset_id,
                "filename": file.filename or "upload.csv",
                "n_rows": body.get("n_rows"),
                "ingest_notes": body.get("ingest_notes"),
            },
            source_service="dataset_service",
        )
    return JSONResponse(body)


# --- Solution / lab research loops (teaching LangGraph) ---

SOLUTION_LOOP_ROOT = Path(
    os.getenv("SOLUTION_LOOP_ROOT", str(ROOT / "solution" / "langgraph"))
)
if not SOLUTION_LOOP_ROOT.exists():
    SOLUTION_LOOP_ROOT = Path("/packages/solution/langgraph")

LAB_LOOP_ROOT = Path(os.getenv("LAB_LOOP_ROOT", str(ROOT / "lab" / "langgraph")))
if not LAB_LOOP_ROOT.exists():
    LAB_LOOP_ROOT = Path("/packages/lab/langgraph")


DEFAULT_OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3.5-lightning:free",
)

# Classroom fallback when OpenRouter /models is unreachable.
_FALLBACK_OPENROUTER_MODELS = [
    {"id": "nvidia/nemotron-3.5-lightning:free", "name": "Nemotron 3.5 Lightning (free)", "free": True},
    {"id": "xingchen-agi/xing4.0-29b-a4b:free", "name": "Xing4.0 29B (free)", "free": True},
    {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B (free)", "free": True},
    {"id": "google/gemma-3-27b-it:free", "name": "Gemma 3 27B (free)", "free": True},
    {"id": "qwen/qwen3-14b:free", "name": "Qwen3 14B (free)", "free": True},
    {"id": "mistralai/mistral-small-3.1-24b-instruct:free", "name": "Mistral Small 3.1 (free)", "free": True},
]


class LoopRequest(BaseModel):
    dataset_path: str | None = None
    target_column: str
    target_score: float = 0.8
    max_cycles: int = 3
    seed: int = 42
    model: str | None = None


def _default_openrouter_model() -> str:
    return (os.getenv("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL).strip()


def _fetch_openrouter_models() -> list[dict]:
    """Return OpenRouter chat models (free first). Falls back offline."""
    import urllib.error
    import urllib.request

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    headers = {
        "Accept": "application/json",
        "HTTP-Referer": "https://localhost/automl-research-lab",
        "X-Title": "Research Loop",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers=headers,
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return list(_FALLBACK_OPENROUTER_MODELS)

    rows: list[dict] = []
    for item in data.get("data") or []:
        mid = str(item.get("id") or "").strip()
        if not mid:
            continue
        pricing = item.get("pricing") or {}
        try:
            free = mid.endswith(":free") or (
                float(pricing.get("prompt") or 0) == 0.0
                and float(pricing.get("completion") or 0) == 0.0
            )
        except (TypeError, ValueError):
            free = mid.endswith(":free")
        name = str(item.get("name") or mid)
        rows.append({"id": mid, "name": name, "free": bool(free)})

    if not rows:
        return list(_FALLBACK_OPENROUTER_MODELS)

    rows.sort(key=lambda r: (not r["free"], r["id"].lower()))
    return rows


def _loop_dataset_dirs() -> list[Path]:
    dirs: list[Path] = []
    for raw in (
        os.getenv("DATASETS_DIR"),
        "/bundled",
        "/bundled/airflow",
        str(ROOT / "datasets"),
        str(ROOT / "datasets" / "airflow"),
        "/tmp/loop_uploads",
    ):
        if not raw:
            continue
        p = Path(raw)
        if p.exists() and p.is_dir() and p not in dirs:
            dirs.append(p)
    return dirs


def _sniff_csv_columns(path: Path, limit: int = 64) -> list[str]:
    import csv

    try:
        with path.open(newline="", encoding="utf-8", errors="replace") as fh:
            sample = fh.read(8192)
            fh.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(fh, dialect)
            row = next(reader, None) or []
    except OSError:
        return []
    cols = [c.strip().strip('"') for c in row if str(c).strip()]
    return cols[:limit]


def _resolve_loop_dataset(explicit: str | None) -> str:
    """Resolve an absolute path or a filename from the datasets catalog."""
    if not explicit or not str(explicit).strip():
        raise HTTPException(
            status_code=400,
            detail="dataset_path required — upload a CSV or pick one from the catalog",
        )
    raw = str(explicit).strip()
    p = Path(raw)
    if p.is_file():
        return str(p.resolve())
    name = Path(raw).name
    if not name or name.startswith(".") or ".." in Path(raw).parts:
        raise HTTPException(status_code=400, detail="invalid dataset name")
    for d in _loop_dataset_dirs():
        cand = d / name
        if cand.is_file():
            return str(cand.resolve())
    raise HTTPException(status_code=400, detail=f"dataset not found: {name}")


def _packages_root() -> Path:
    """Parent of lab/ and solution/ packages (repo root locally, /packages in Docker)."""
    for candidate in (SOLUTION_LOOP_ROOT.parent.parent, LAB_LOOP_ROOT.parent.parent, Path("/packages"), ROOT):
        if (candidate / "solution" / "langgraph" / "graph.py").exists() or (
            candidate / "lab" / "langgraph" / "graph.py"
        ).exists():
            return candidate
    return ROOT


def _import_loop_graph(module: str, root: Path, label: str):
    if not (root / "graph.py").exists():
        raise HTTPException(status_code=503, detail=f"{label} missing at {root}")
    pkg_root = _packages_root()
    if str(pkg_root) not in sys.path:
        sys.path.insert(0, str(pkg_root))
    for name in list(sys.modules):
        if name in {"lab", "solution", "loop_runtime"} or name.startswith("lab.") or name.startswith(
            "solution."
        ):
            del sys.modules[name]
    try:
        return importlib.import_module(module)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"cannot import {module}: {exc}") from exc


def _import_solution_loop():
    return _import_loop_graph("solution.langgraph.graph", SOLUTION_LOOP_ROOT, "solution loop")


def _import_lab_loop():
    return _import_loop_graph("lab.langgraph.graph", LAB_LOOP_ROOT, "lab loop")


def _loop_dataset_label(dataset_abs: str, requested: str | None) -> str:
    if requested and str(requested).strip():
        return Path(str(requested).strip()).name
    return Path(dataset_abs).name


def _record_loop_run(
    *,
    dataset_label: str,
    target_column: str,
    target_score: float,
    max_cycles: int,
    result: dict | None = None,
    error: str | None = None,
    model: str | None = None,
) -> dict:
    holdout = (result or {}).get("holdout_metrics") or {}
    verdict = (result or {}).get("verdict") or {}
    return loop_run_store.append(
        {
            "status": "error" if error else "completed",
            "dataset": dataset_label,
            "target_column": target_column,
            "target_score": target_score,
            "max_cycles": max_cycles,
            "cycles": (result or {}).get("cycles"),
            "best_val_f1": (result or {}).get("best_val_f1"),
            "holdout_f1": holdout.get("f1") if isinstance(holdout, dict) else None,
            "stop_reason": (result or {}).get("stop_reason"),
            "model": (model or "").strip() or _default_openrouter_model(),
            "verdict_action": verdict.get("action") if isinstance(verdict, dict) else None,
            "error": error,
            "result": result if isinstance(result, dict) else None,
        }
    )


@app.get("/solution-loop/info")
def solution_loop_info() -> dict:
    return {
        "root": str(SOLUTION_LOOP_ROOT),
        "available": (SOLUTION_LOOP_ROOT / "graph.py").exists(),
        "accepts": "any CSV with a target column",
        "nodes": [
            "data_scientist",
            "hypothesis_generator",
            "ml_engineer",
            "judge",
            "memory_writer",
            "context_builder",
            "holdout_eval",
        ],
        "router": "conditional edge accept|revise|reject",
        "llm": {
            "provider": "openrouter",
            "model": _default_openrouter_model(),
            "key_configured": bool(os.getenv("OPENROUTER_API_KEY")),
        },
        "datasets": [
            {"filename": p.name, "columns": _sniff_csv_columns(p)}
            for d in _loop_dataset_dirs()
            for p in sorted(d.glob("*.csv"))
        ],
    }


@app.get("/solution-loop/models")
def solution_loop_models() -> dict:
    """Models for the solution-loop agent dropdown (Cursor SDK + OpenRouter)."""
    cursor_ok = bool(os.getenv("CURSOR_API_KEY", "").strip())
    openrouter_ok = bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    default = "cursor/composer-2.5" if cursor_ok else _default_openrouter_model()
    cursor_models = [
        {
            "id": "cursor/composer-2.5",
            "name": "Cursor Composer 2.5 (SDK)",
            "free": False,
            "provider": "cursor",
            "available": cursor_ok,
        }
    ]
    openrouter = [
        {**m, "provider": "openrouter", "available": openrouter_ok}
        for m in _fetch_openrouter_models()
    ]
    models = [*cursor_models, *openrouter]
    ids = {m["id"] for m in models}
    env_default = _default_openrouter_model()
    if env_default not in ids:
        models.insert(
            1 if env_default.startswith("cursor/") else len(cursor_models),
            {
                "id": env_default,
                "name": env_default,
                "free": env_default.endswith(":free"),
                "provider": "cursor" if env_default.startswith("cursor/") else "openrouter",
                "available": cursor_ok if env_default.startswith("cursor/") else openrouter_ok,
            },
        )
    return {
        "default": default,
        "cursor_configured": cursor_ok,
        "key_configured": openrouter_ok,
        "models": models,
    }


@app.get("/solution-loop/datasets")
def solution_loop_datasets() -> dict:
    seen: set[str] = set()
    items: list[dict] = []
    for d in _loop_dataset_dirs():
        for p in sorted(d.glob("*.csv")):
            if p.name in seen:
                continue
            seen.add(p.name)
            items.append(
                {
                    "filename": p.name,
                    "path": str(p.resolve()),
                    "columns": _sniff_csv_columns(p),
                    "bytes": p.stat().st_size,
                }
            )
    return {"datasets": items}


@app.post("/solution-loop/dataset")
async def solution_loop_upload_dataset(file: UploadFile = File(...)) -> JSONResponse:
    """Stage any CSV for the research loop (returns path + columns)."""
    name = Path(file.filename or "upload.csv").name
    if not name.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="only .csv uploads are supported")
    if ".." in Path(name).parts:
        raise HTTPException(status_code=400, detail="invalid filename")

    dest_dirs = _loop_dataset_dirs()
    dest_root = next(
        (d for d in dest_dirs if d.exists() and os.access(d, os.W_OK)),
        None,
    )
    if dest_root is None:
        dest_root = Path("/tmp/loop_uploads")
        dest_root.mkdir(parents=True, exist_ok=True)

    dest = dest_root / name
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    dest.write_bytes(raw)
    cols = _sniff_csv_columns(dest)
    return JSONResponse(
        {
            "filename": name,
            "path": str(dest.resolve()),
            "columns": cols,
            "bytes": len(raw),
        }
    )


@app.get("/solution-loop/runs")
def solution_loop_list_runs(limit: int = Query(default=50, ge=1, le=50)) -> dict:
    return {"runs": loop_run_store.list_runs(limit=limit)}


@app.get("/solution-loop/runs/{run_id}")
def solution_loop_get_run(run_id: str) -> dict:
    row = loop_run_store.get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return row


@app.post("/solution-loop/run")
async def solution_loop_run(body: LoopRequest) -> JSONResponse:
    """Run the solution LangGraph reference implementation."""
    dataset = _resolve_loop_dataset(body.dataset_path)
    label = _loop_dataset_label(dataset, body.dataset_path)
    model = (body.model or "").strip() or _default_openrouter_model()
    graph_mod = _import_solution_loop()
    try:
        result = graph_mod.run_solution_loop(
            dataset_path=dataset,
            target_column=body.target_column,
            target_score=body.target_score,
            max_cycles=body.max_cycles,
            seed=body.seed,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001
        _record_loop_run(
            dataset_label=label,
            target_column=body.target_column,
            target_score=body.target_score,
            max_cycles=body.max_cycles,
            error=str(exc),
            model=model,
        )
        raise HTTPException(status_code=500, detail=f"solution-loop failed: {exc}") from exc
    _record_loop_run(
        dataset_label=label,
        target_column=body.target_column,
        target_score=body.target_score,
        max_cycles=body.max_cycles,
        result=result if isinstance(result, dict) else {},
        model=model,
    )
    return JSONResponse(result)


@app.get("/solution-loop/stream")
async def solution_loop_stream(
    target_column: str = Query(..., min_length=1),
    dataset_path: str = Query(..., min_length=1),
    target_score: float = Query(default=0.8),
    max_cycles: int = Query(default=3, ge=1, le=8),
    seed: int = Query(default=42),
    model: str | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream of LangGraph node events for the solution-loop UI."""
    dataset = _resolve_loop_dataset(dataset_path)
    label = _loop_dataset_label(dataset, dataset_path)
    chosen_model = (model or "").strip() or _default_openrouter_model()
    graph_mod = _import_solution_loop()

    def event_stream():
        saved = False
        try:
            for ev in graph_mod.stream_solution_loop(
                dataset_path=dataset,
                target_column=target_column,
                target_score=target_score,
                max_cycles=max_cycles,
                seed=seed,
                model=chosen_model,
            ):
                etype = str(ev.get("type") or "message")
                if etype == "run_completed" and not saved:
                    result = ev.get("result") if isinstance(ev, dict) else None
                    _record_loop_run(
                        dataset_label=label,
                        target_column=target_column,
                        target_score=target_score,
                        max_cycles=max_cycles,
                        result=result if isinstance(result, dict) else {},
                        model=chosen_model,
                    )
                    saved = True
                if etype == "error" and not saved:
                    _record_loop_run(
                        dataset_label=label,
                        target_column=target_column,
                        target_score=target_score,
                        max_cycles=max_cycles,
                        error=str(ev.get("message") or "stream error"),
                        model=chosen_model,
                    )
                    saved = True
                yield f"event: {etype}\n"
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001
            if not saved:
                _record_loop_run(
                    dataset_label=label,
                    target_column=target_column,
                    target_score=target_score,
                    max_cycles=max_cycles,
                    error=str(exc),
                    model=chosen_model,
                )
            err = {"type": "error", "message": str(exc)}
            yield "event: error\n"
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# --- Lab research loop (classroom skeleton; empty until wired) ---


@app.get("/lab-loop/status")
def lab_loop_status() -> dict:
    """Readiness for the Lab Loop UI (empty canvas until ready)."""
    base = {
        "root": str(LAB_LOOP_ROOT),
        "available": (LAB_LOOP_ROOT / "graph.py").exists(),
    }
    if not base["available"]:
        return {
            **base,
            "ready": False,
            "nodes": [],
            "missing_nodes": [],
            "error": "lab/langgraph/graph.py not found",
        }
    lab_graph = _import_lab_loop()
    status = lab_graph.get_status()
    return {**base, **status}


@app.get("/lab-loop/stream")
async def lab_loop_stream(
    target_column: str = Query(..., min_length=1),
    dataset_path: str = Query(..., min_length=1),
    target_score: float = Query(default=0.8),
    max_cycles: int = Query(default=3, ge=1, le=8),
    seed: int = Query(default=42),
    model: str | None = Query(default=None),
) -> StreamingResponse:
    """SSE stream for the lab skeleton graph (same panels as solution-loop)."""
    dataset = _resolve_loop_dataset(dataset_path)
    label = _loop_dataset_label(dataset, dataset_path)
    chosen_model = (model or "").strip() or _default_openrouter_model()
    lab_graph = _import_lab_loop()
    status = lab_graph.get_status()
    if not status.get("ready"):
        raise HTTPException(
            status_code=400,
            detail=status.get("error") or "lab graph not ready — wire build_graph() first",
        )

    def event_stream():
        saved = False
        try:
            for ev in lab_graph.stream_lab_loop(
                dataset_path=dataset,
                target_column=target_column,
                target_score=target_score,
                max_cycles=max_cycles,
                seed=seed,
                model=chosen_model,
            ):
                etype = str(ev.get("type") or "message")
                if etype == "run_completed" and not saved:
                    result = ev.get("result") if isinstance(ev, dict) else None
                    _record_loop_run(
                        dataset_label=f"[lab] {label}",
                        target_column=target_column,
                        target_score=target_score,
                        max_cycles=max_cycles,
                        result=result if isinstance(result, dict) else {},
                        model=chosen_model,
                    )
                    saved = True
                if etype == "error" and not saved:
                    _record_loop_run(
                        dataset_label=f"[lab] {label}",
                        target_column=target_column,
                        target_score=target_score,
                        max_cycles=max_cycles,
                        error=str(ev.get("message") or "stream error"),
                        model=chosen_model,
                    )
                    saved = True
                yield f"event: {etype}\n"
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001
            if not saved:
                _record_loop_run(
                    dataset_label=f"[lab] {label}",
                    target_column=target_column,
                    target_score=target_score,
                    max_cycles=max_cycles,
                    error=str(exc),
                    model=chosen_model,
                )
            err = {"type": "error", "message": str(exc)}
            yield "event: error\n"
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
