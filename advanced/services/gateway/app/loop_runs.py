"""Persistent lab/solution loop run history (JSON on disk)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _default_path() -> Path:
    raw = os.getenv("LOOP_RUNS_PATH", "").strip() or os.getenv("SIMPLE_LOOP_RUNS_PATH", "").strip()
    if raw:
        return Path(raw)
    # Prefer /data when the Docker volume exists; else repo-local fallback.
    docker = Path("/data/loop_runs/runs.json")
    if Path("/data").exists():
        return docker
    # advanced/services/gateway/app -> parents[4] = repo root
    return Path(__file__).resolve().parents[4] / "data" / "loop_runs" / "runs.json"


MAX_RUNS = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LoopRunStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or _default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._runs: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        runs = data.get("runs") if isinstance(data, dict) else None
        if isinstance(runs, list):
            self._runs = [r for r in runs if isinstance(r, dict)]

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"runs": self._runs}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        run_id = str(record.get("run_id") or f"slr_{uuid.uuid4().hex[:12]}")
        entry = {
            "run_id": run_id,
            "created_at": record.get("created_at") or _now_iso(),
            "status": record.get("status") or "completed",
            "dataset": record.get("dataset"),
            "target_column": record.get("target_column"),
            "target_score": record.get("target_score"),
            "max_cycles": record.get("max_cycles"),
            "cycles": record.get("cycles"),
            "best_val_f1": record.get("best_val_f1"),
            "holdout_f1": record.get("holdout_f1"),
            "stop_reason": record.get("stop_reason"),
            "model": record.get("model"),
            "verdict_action": record.get("verdict_action"),
            "error": record.get("error"),
            # Full loop payload for UI replay (timeline / agent outputs).
            "result": record.get("result"),
        }
        with self._lock:
            self._runs.insert(0, entry)
            if len(self._runs) > MAX_RUNS:
                self._runs = self._runs[:MAX_RUNS]
            self._save()
        return entry

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._runs[: max(1, min(limit, MAX_RUNS))])

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            for row in self._runs:
                if row.get("run_id") == run_id:
                    return dict(row)
        return None


loop_run_store = LoopRunStore()
