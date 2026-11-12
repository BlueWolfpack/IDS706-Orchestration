"""Seven validated tools — the only execution interface agents get."""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any

import httpx
import joblib
import pandas as pd

from services.harness.app.backends import run_trial
from services.harness.app.policy import POLICY

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")
HARNESS_TOKEN = os.getenv("HARNESS_TOKEN", SERVICE_TOKEN)
DATASET_URL = os.getenv("DATASET_SERVICE_URL", "http://dataset_service:8004")
ARTIFACT_ROOT = Path(os.getenv("ARTIFACT_ROOT", "/artifacts"))

_lock = threading.Lock()
_idempotency: dict[str, dict[str, Any]] = {}
_history: list[dict[str, Any]] = []
_executor = ThreadPoolExecutor(max_workers=2)


def _headers() -> dict[str, str]:
    return {"X-Service-Token": SERVICE_TOKEN, "X-Harness-Token": HARNESS_TOKEN}


def inspect_data(dataset_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        r = client.get(f"{DATASET_URL}/datasets/{dataset_id}/profile-view", headers=_headers())
        r.raise_for_status()
        return r.json()


def validate_experiment(spec: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    family = spec.get("model_family")
    if family not in POLICY.allowed_model_families:
        errors.append(f"model_family {family!r} not allowed")
    hp = spec.get("hyperparameters") or {}
    if family == "random_forest" and hp.get("max_depth") is not None:
        try:
            if int(hp["max_depth"]) < 1:
                errors.append("max_depth must be null or >= 1")
        except (TypeError, ValueError):
            errors.append("max_depth must be an int or null")
    return {"valid": not errors, "errors": errors, "mock": False}


def _run_once(
    session_id: str,
    dataset_id: str,
    target_column: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    with httpx.Client(timeout=180.0) as client:
        train_r = client.get(
            f"{DATASET_URL}/datasets/{dataset_id}/splits/train", headers=_headers()
        )
        val_r = client.get(
            f"{DATASET_URL}/datasets/{dataset_id}/splits/validation", headers=_headers()
        )
        train_r.raise_for_status()
        val_r.raise_for_status()
        train = pd.DataFrame(train_r.json()["rows"])
        validation = pd.DataFrame(val_r.json()["rows"])

    profile = inspect_data(dataset_id)
    drop = list(profile.get("identifier_columns") or [])

    experiment_id = str(spec.get("experiment_id") or f"e-{uuid.uuid4().hex[:8]}")
    pipe, train_metrics, val_metrics, duration = run_trial(
        train=train,
        validation=validation,
        target=target_column,
        model_family=str(spec["model_family"]),
        hyperparameters=dict(spec.get("hyperparameters") or {}),
        drop_columns=drop,
    )

    out_dir = ARTIFACT_ROOT / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / f"{experiment_id}.joblib"
    joblib.dump(pipe, model_path)
    meta_path = out_dir / f"{experiment_id}.json"
    meta_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "dataset_id": dataset_id,
                "experiment_id": experiment_id,
                "spec": spec,
                "train_metrics": train_metrics,
                "validation_metrics": val_metrics,
            },
            indent=2,
        )
    )

    return {
        "experiment_id": experiment_id,
        "status": "succeeded",
        "train_metrics": train_metrics,
        "validation_metrics": val_metrics,
        "duration_seconds": duration,
        "artifact_ids": [str(model_path)],
        "model_ref": str(model_path),
        "error": None,
        "mock": False,
    }


def run_experiment(
    session_id: str,
    dataset_id: str,
    target_column: str,
    spec: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    with _lock:
        if idempotency_key in _idempotency:
            return _idempotency[idempotency_key]

    check = validate_experiment(spec)
    if not check["valid"]:
        result = {
            "experiment_id": spec.get("experiment_id") or f"e-{uuid.uuid4().hex[:8]}",
            "status": "failed",
            "error": "; ".join(check["errors"]),
            "train_metrics": {},
            "validation_metrics": {},
            "duration_seconds": 0.0,
            "artifact_ids": [],
            "model_ref": None,
            "mock": False,
        }
        with _lock:
            _idempotency[idempotency_key] = result
            _history.append(result)
        return result

    try:
        timeout = int(spec.get("timeout_seconds") or POLICY.per_trial_timeout_seconds)
        future = _executor.submit(_run_once, session_id, dataset_id, target_column, spec)
        result = future.result(timeout=timeout)
    except FuturesTimeout:
        timeout = int(spec.get("timeout_seconds") or POLICY.per_trial_timeout_seconds)
        result = {
            "experiment_id": spec.get("experiment_id") or f"e-{uuid.uuid4().hex[:8]}",
            "status": "failed",
            "error": f"per_trial_timeout_seconds={timeout} exceeded",
            "train_metrics": {},
            "validation_metrics": {},
            "duration_seconds": float(timeout),
            "artifact_ids": [],
            "model_ref": None,
            "mock": False,
        }
    except Exception as exc:  # noqa: BLE001 — surface as tool failure for agents
        result = {
            "experiment_id": spec.get("experiment_id") or f"e-{uuid.uuid4().hex[:8]}",
            "status": "failed",
            "error": str(exc),
            "train_metrics": {},
            "validation_metrics": {},
            "duration_seconds": 0.0,
            "artifact_ids": [],
            "model_ref": None,
            "mock": False,
        }

    with _lock:
        _idempotency[idempotency_key] = result
        _history.append(result)
    return result


def compare_experiments(experiment_ids: list[str]) -> dict[str, Any]:
    items = [h for h in _history if h.get("experiment_id") in experiment_ids]
    return {"comparison": {"items": items}, "mock": False}


def get_history(session_id: str, limit: int = 50) -> dict[str, Any]:
    items = list(reversed(_history))[:limit]
    return {"items": items, "session_id": session_id, "mock": False}


def save_artifact(
    name: str, artifact_type: str, metadata: dict[str, Any], idempotency_key: str
) -> dict[str, Any]:
    with _lock:
        if idempotency_key in _idempotency:
            return _idempotency[idempotency_key]
    artifact_id = f"art-{uuid.uuid4().hex[:10]}"
    path = ARTIFACT_ROOT / "misc" / f"{artifact_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"name": name, "type": artifact_type, "metadata": metadata}, indent=2)
    )
    result = {"artifact_id": artifact_id, "path": str(path), "mock": False}
    with _lock:
        _idempotency[idempotency_key] = result
    return result


def generate_report(session_id: str, idempotency_key: str) -> dict[str, Any]:
    with _lock:
        if idempotency_key in _idempotency:
            return _idempotency[idempotency_key]
    report_id = f"rep-{uuid.uuid4().hex[:8]}"
    path = ARTIFACT_ROOT / "reports" / f"{report_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Report {report_id}", f"session: {session_id}", "", "## Trials"]
    for item in _history[-20:]:
        lines.append(
            f"- {item.get('experiment_id')}: val f1="
            f"{(item.get('validation_metrics') or {}).get('f1', 'n/a')}"
        )
    path.write_text("\n".join(lines))
    result = {
        "report_id": report_id,
        "local_path": str(path),
        "wandb_url": None,
        "mock": False,
        "note": "W&B report MCP optional in C3/C5",
    }
    with _lock:
        _idempotency[idempotency_key] = result
    return result
