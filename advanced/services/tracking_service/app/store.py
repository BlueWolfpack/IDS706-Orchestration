"""MLflow logging + optional W&B mirror. Never log WANDB_API_KEY."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
WANDB_ENABLED = os.getenv("WANDB_ENABLED", "false").lower() in {"1", "true", "yes"}
WANDB_PROJECT = os.getenv("WANDB_PROJECT", "automl-research-lab")
WANDB_ENTITY = os.getenv("WANDB_ENTITY") or None

_lock = threading.Lock()
_idempotency: dict[str, dict[str, Any]] = {}
_runs: dict[str, dict[str, Any]] = {}
_by_session: dict[str, list[str]] = {}
_mlflow_ready = False


def _init_mlflow() -> None:
    global _mlflow_ready
    uri = MLFLOW_TRACKING_URI
    # Local sqlite fallback for unit tests without the MLflow container.
    if os.getenv("MLFLOW_LOCAL_FALLBACK", "").lower() in {"1", "true", "yes"}:
        local = os.getenv("MLFLOW_LOCAL_DIR", "/tmp/automl-mlflow")
        os.makedirs(local, exist_ok=True)
        uri = f"sqlite:///{local}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    _mlflow_ready = True


def _maybe_wandb_log(
    experiment_id: str,
    config: dict[str, Any],
    metrics: dict[str, float],
    tags: dict[str, str],
) -> str | None:
    if not WANDB_ENABLED:
        return None
    if not os.getenv("WANDB_API_KEY"):
        return None
    try:
        import wandb

        run = wandb.init(
            project=WANDB_PROJECT,
            entity=WANDB_ENTITY,
            name=experiment_id,
            config=config,
            tags=[f"{k}:{v}" for k, v in tags.items()],
            reinit=True,
            settings=wandb.Settings(silent=True),
        )
        if metrics:
            wandb.log(metrics)
        url = run.get_url()
        # Holdout / final runs stay tagged; agents must never query final via MCP.
        wandb.finish()
        return url
    except Exception:  # noqa: BLE001 — W&B is optional; never fail the trial log
        return None


def create_run(
    session_id: str,
    experiment_id: str,
    config: dict[str, Any],
    metrics: dict[str, float],
    tags: dict[str, str],
    idempotency_key: str,
) -> dict[str, Any]:
    with _lock:
        if idempotency_key in _idempotency:
            return _idempotency[idempotency_key]

    _init_mlflow()
    exp_name = f"automl-{session_id}"
    mlflow.set_experiment(exp_name)
    with mlflow.start_run(run_name=experiment_id) as active:
        mlflow_run_id = active.info.run_id
        if config:
            mlflow.log_params({k: str(v)[:250] for k, v in config.items()})
        if metrics:
            mlflow.log_metrics({k: float(v) for k, v in metrics.items()})
        for k, v in tags.items():
            mlflow.set_tag(k, v)
        mlflow.set_tag("session_id", session_id)
        mlflow.set_tag("experiment_id", experiment_id)

    wandb_url = _maybe_wandb_log(experiment_id, config, metrics, tags)
    run_id = f"trk-{uuid.uuid4().hex[:10]}"
    record = {
        "run_id": run_id,
        "mlflow_run_id": mlflow_run_id,
        "session_id": session_id,
        "experiment_id": experiment_id,
        "config": config,
        "metrics": metrics,
        "tags": tags,
        "wandb_url": wandb_url,
        "mock": False,
    }
    with _lock:
        _idempotency[idempotency_key] = record
        _runs[run_id] = record
        _by_session.setdefault(session_id, []).append(run_id)
    return record


def get_run(run_id: str) -> dict[str, Any] | None:
    with _lock:
        return _runs.get(run_id)


def list_session(session_id: str) -> list[dict[str, Any]]:
    with _lock:
        ids = list(_by_session.get(session_id, []))
        return [_runs[i] for i in ids if i in _runs]


def mlflow_reachable() -> bool:
    try:
        _init_mlflow()
        MlflowClient(MLFLOW_TRACKING_URI).search_experiments(max_results=1)
        return True
    except Exception:  # noqa: BLE001
        return False
