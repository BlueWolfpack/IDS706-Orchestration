"""Persistent project + training-session registry (JSON on disk)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contracts.projects import (
    PriorDataset,
    ProjectDetail,
    ProjectSummary,
    TrainingSessionRecord,
)

_DEFAULT_ROOT = Path(os.getenv("PROJECT_DATA_DIR", "/data/projects"))
if not _DEFAULT_ROOT.parent.exists() and not str(_DEFAULT_ROOT).startswith("/data"):
    _DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "projects"
elif str(_DEFAULT_ROOT).startswith("/data") and not Path("/data").exists():
    _DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "projects"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "registry.json"
        self._lock = threading.Lock()
        self._projects: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        self._projects = {p["project_id"]: p for p in data.get("projects", [])}
        self._sessions = {s["session_id"]: s for s in data.get("sessions", [])}

    def _save(self) -> None:
        payload = {
            "projects": list(self._projects.values()),
            "sessions": list(self._sessions.values()),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        tmp.replace(self.path)

    def create_project(self, name: str, description: str = "") -> ProjectSummary:
        pid = f"proj-{uuid.uuid4().hex[:10]}"
        now = _now()
        rec = {
            "project_id": pid,
            "name": name.strip(),
            "description": (description or "").strip(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        with self._lock:
            self._projects[pid] = rec
            self._save()
        return self._summary(rec)

    def list_projects(self) -> list[ProjectSummary]:
        with self._lock:
            projects = list(self._projects.values())
            sessions = list(self._sessions.values())
        out = [self._summary(p, sessions) for p in projects]
        out.sort(key=lambda p: p.updated_at, reverse=True)
        return out

    def get_project(self, project_id: str) -> ProjectDetail | None:
        with self._lock:
            p = self._projects.get(project_id)
            if p is None:
                return None
            sess = [s for s in self._sessions.values() if s.get("project_id") == project_id]
        summary = self._summary(p, sess)
        records = [self._session_model(s) for s in sess]
        records.sort(key=lambda s: s.created_at, reverse=True)
        return ProjectDetail(**summary.model_dump(), sessions=records)

    def prior_datasets(self, project_id: str) -> list[PriorDataset]:
        """Unique filenames previously used on this project (most recent first)."""
        with self._lock:
            if project_id not in self._projects:
                return []
            sess = [s for s in self._sessions.values() if s.get("project_id") == project_id]
        by_name: dict[str, PriorDataset] = {}
        for s in sess:
            name = (s.get("dataset_filename") or "").strip()
            if not name or name in {"mock-fixture", "replay"}:
                continue
            used_at = _parse_dt(s.get("updated_at") or s.get("created_at"))
            existing = by_name.get(name)
            if existing is None:
                by_name[name] = PriorDataset(
                    filename=name,
                    target_column=s.get("target_column") or None,
                    times_used=1,
                    last_used_at=used_at,
                    source="project_history",
                )
            else:
                existing.times_used += 1
                if used_at and (existing.last_used_at is None or used_at > existing.last_used_at):
                    existing.last_used_at = used_at
                    if s.get("target_column"):
                        existing.target_column = s.get("target_column")
        return sorted(
            by_name.values(),
            key=lambda d: d.last_used_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

    def ensure_project(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._projects

    def register_session(
        self,
        *,
        session_id: str,
        project_id: str,
        target_column: str,
        mode: str = "live",
        mock: bool = False,
        replay: bool = False,
        task_type: str = "classification",
        metric: str = "f1",
        target_score: float = 0.7,
        experiment_budget: int = 5,
        dataset_filename: str | None = None,
        dataset_id: str | None = None,
        status: str = "created",
        research_strategy: str = "model_search",
        fixed_model_family: str | None = None,
        per_trial_timeout_seconds: int = 120,
    ) -> TrainingSessionRecord:
        now = _now()
        rec = {
            "session_id": session_id,
            "project_id": project_id,
            "status": status,
            "mode": mode,
            "mock": mock,
            "replay": replay,
            "dataset_filename": dataset_filename,
            "dataset_id": dataset_id,
            "target_column": target_column,
            "task_type": task_type,
            "metric": metric,
            "target_score": target_score,
            "experiment_budget": experiment_budget,
            "experiments_used": 0,
            "research_strategy": research_strategy,
            "fixed_model_family": fixed_model_family,
            "per_trial_timeout_seconds": per_trial_timeout_seconds,
            "best_val_score": None,
            "holdout_score": None,
            "stop_reason": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "completed_at": None,
        }
        with self._lock:
            if project_id not in self._projects:
                raise KeyError(f"project {project_id} not found")
            self._sessions[session_id] = rec
            self._projects[project_id]["updated_at"] = now.isoformat()
            self._save()
        return self._session_model(rec)

    def update_session(self, session_id: str, **fields: Any) -> TrainingSessionRecord | None:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return None
            for k, v in fields.items():
                if v is not None or k in {
                    "best_val_score",
                    "holdout_score",
                    "stop_reason",
                    "dataset_filename",
                    "dataset_id",
                    "completed_at",
                }:
                    rec[k] = v
            rec["updated_at"] = _now().isoformat()
            status = rec.get("status")
            if status in {"completed", "failed", "reset"} and not rec.get("completed_at"):
                rec["completed_at"] = rec["updated_at"]
            pid = rec.get("project_id")
            if pid and pid in self._projects:
                self._projects[pid]["updated_at"] = rec["updated_at"]
            self._save()
            return self._session_model(rec)

    def get_session(self, session_id: str) -> TrainingSessionRecord | None:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None:
                return None
            return self._session_model(rec)

    def _summary(
        self,
        project: dict[str, Any],
        sessions: list[dict[str, Any]] | None = None,
    ) -> ProjectSummary:
        sess = sessions if sessions is not None else [
            s for s in self._sessions.values() if s.get("project_id") == project["project_id"]
        ]
        last = None
        best = None
        for s in sess:
            ts = _parse_dt(s.get("created_at"))
            if ts and (last is None or ts > last):
                last = ts
            score = s.get("best_val_score")
            if isinstance(score, (int, float)):
                best = score if best is None else max(best, float(score))
        return ProjectSummary(
            project_id=project["project_id"],
            name=project["name"],
            description=project.get("description") or "",
            created_at=_parse_dt(project["created_at"]) or _now(),
            updated_at=_parse_dt(project["updated_at"]) or _now(),
            session_count=len(sess),
            last_session_at=last,
            best_val_score=best,
        )

    def _session_model(self, rec: dict[str, Any]) -> TrainingSessionRecord:
        return TrainingSessionRecord(
            session_id=rec["session_id"],
            project_id=rec["project_id"],
            status=rec.get("status") or "created",
            mode=rec.get("mode") or "live",
            mock=bool(rec.get("mock")),
            replay=bool(rec.get("replay")),
            dataset_filename=rec.get("dataset_filename"),
            dataset_id=rec.get("dataset_id"),
            target_column=rec.get("target_column") or "",
            task_type=rec.get("task_type") or "classification",
            metric=rec.get("metric") or "f1",
            target_score=float(rec.get("target_score") or 0.7),
            experiment_budget=int(rec.get("experiment_budget") or 5),
            experiments_used=int(rec.get("experiments_used") or 0),
            research_strategy=str(rec.get("research_strategy") or "model_search"),
            fixed_model_family=rec.get("fixed_model_family"),
            per_trial_timeout_seconds=int(rec.get("per_trial_timeout_seconds") or 120),
            best_val_score=rec.get("best_val_score"),
            holdout_score=rec.get("holdout_score"),
            stop_reason=rec.get("stop_reason"),
            created_at=_parse_dt(rec.get("created_at")) or _now(),
            updated_at=_parse_dt(rec.get("updated_at")) or _now(),
            completed_at=_parse_dt(rec.get("completed_at")),
        )


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


project_store = ProjectStore(_DEFAULT_ROOT)
