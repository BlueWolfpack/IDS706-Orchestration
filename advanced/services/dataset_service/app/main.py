"""Dataset-service — owns uploads, fixed splits, sealed holdout (Stage C1)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services"))

from contracts import HealthResponse  # noqa: E402
from _shared.correlation import CorrelationIdMiddleware  # noqa: E402
from services.dataset_service.app.store import DatasetStore  # noqa: E402

SERVICE_NAME = "dataset_service"
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")
HARNESS_TOKEN = os.getenv("HARNESS_TOKEN", SERVICE_TOKEN)
DATA_ROOT = Path(os.getenv("DATASET_DATA_DIR", str(ROOT / "data" / "datasets")))

store = DatasetStore(DATA_ROOT)

app = FastAPI(title="AutoML Dataset Service", version="0.2.0")
app.add_middleware(CorrelationIdMiddleware)


class HoldoutEvaluateRequest(BaseModel):
    session_id: str
    dataset_id: str
    model_ref: str  # filesystem path to joblib pipeline, known to harness
    metric: str = "f1"
    idempotency_key: str


def _check_service_token(authorization: str | None, x_service_token: str | None) -> None:
    token = x_service_token or (authorization or "").removeprefix("Bearer ").strip()
    if token != SERVICE_TOKEN:
        raise HTTPException(status_code=401, detail="invalid service token")


def _check_harness_token(x_harness_token: str | None, x_service_token: str | None) -> None:
    token = x_harness_token or x_service_token
    if token != HARNESS_TOKEN:
        raise HTTPException(status_code=401, detail="harness token required for holdout evaluate")


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service=SERVICE_NAME, mock=False)


@app.post("/datasets", status_code=status.HTTP_201_CREATED)
async def create_dataset(
    file: UploadFile = File(...),
    target_column: str = Form(...),
    task_type: str = Form("classification"),
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    authorization: str | None = Header(default=None),
) -> dict:
    _check_service_token(authorization, x_service_token)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        rec = store.create_from_csv(
            raw=raw,
            filename=file.filename or "upload.csv",
            target_column=target_column,
            task_type=task_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "dataset_id": rec.dataset_id,
        "filename": rec.filename,
        "n_rows": rec.n_rows,
        "n_columns": rec.n_columns,
        "target_column": rec.target_column,
        "task_type": rec.task_type,
        "ingest_notes": rec.ingest_notes,
        "mock": False,
    }


@app.get("/datasets/{dataset_id}/profile-view")
def profile_view(
    dataset_id: str,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    authorization: str | None = Header(default=None),
) -> dict:
    _check_service_token(authorization, x_service_token)
    try:
        return store.profile_view(dataset_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset not found") from None


@app.get("/datasets/{dataset_id}/splits/{name}")
def get_split(
    dataset_id: str,
    name: str,
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    _check_service_token(authorization, x_service_token)
    if name == "holdout":
        # Explicit denial — teaching point for the sealed holdout.
        raise HTTPException(status_code=403, detail="holdout rows are not readable")
    try:
        df = store.read_split(dataset_id, name)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="split not found") from None
    # NaNs (common in Kaggle CSVs) are not JSON-compliant — emit nulls instead.
    records = json.loads(df.to_json(orient="records", date_format="iso"))
    return JSONResponse(
        {
            "dataset_id": dataset_id,
            "split": name,
            "n_rows": int(len(df)),
            "columns": list(df.columns),
            "rows": records,
            "mock": False,
        }
    )


@app.post("/internal/holdout/evaluate")
def holdout_evaluate(
    body: HoldoutEvaluateRequest,
    x_harness_token: str | None = Header(default=None, alias="X-Harness-Token"),
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> dict:
    _check_harness_token(x_harness_token, x_service_token)
    try:
        return store.evaluate_holdout(
            dataset_id=body.dataset_id,
            session_id=body.session_id,
            model_path=body.model_ref,
            metric=body.metric,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="dataset or model not found") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
