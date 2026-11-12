"""Four memory stores with single-writer enforcement."""

from __future__ import annotations

import threading
import uuid
from typing import Any


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.findings: dict[str, list[dict[str, Any]]] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.lessons: list[dict[str, Any]] = []
        self.working: dict[str, dict[str, dict[str, Any]]] = {}  # agent -> session -> content
        self._writers: dict[str, str] = {}  # resource key -> writer
        self._idempotency: dict[str, dict[str, Any]] = {}

    def _claim_writer(self, resource: str, writer: str) -> None:
        existing = self._writers.get(resource)
        if existing is None:
            self._writers[resource] = writer
            return
        if existing != writer:
            raise PermissionError(f"single-writer: {resource} owned by {existing}, not {writer}")

    def write_findings(
        self, session_id: str, writer: str, content: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            self._claim_writer(f"findings:{session_id}", writer)
            item = {"id": f"f-{uuid.uuid4().hex[:8]}", "session_id": session_id, "writer": writer, **content}
            self.findings.setdefault(session_id, []).append(item)
            result = {"ok": True, "item": item, "mock": False}
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result

    def get_findings(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return {"session_id": session_id, "items": list(self.findings.get(session_id, [])), "mock": False}

    def write_history(
        self, session_id: str, writer: str, content: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            self._claim_writer(f"history:{session_id}", writer)
            item = {"id": f"h-{uuid.uuid4().hex[:8]}", "session_id": session_id, "writer": writer, **content}
            self.history.setdefault(session_id, []).append(item)
            result = {"ok": True, "item": item, "mock": False}
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result

    def get_history(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return {"session_id": session_id, "items": list(self.history.get(session_id, [])), "mock": False}

    def write_lesson(
        self, writer: str, content: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            self._claim_writer("lessons:global", writer)
            item = {"id": f"l-{uuid.uuid4().hex[:8]}", "writer": writer, **content}
            self.lessons.append(item)
            result = {"ok": True, "item": item, "mock": False}
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result

    def search_lessons(self, q: str) -> dict[str, Any]:
        q_l = (q or "").lower()
        with self._lock:
            if not q_l:
                items = list(self.lessons)
            else:
                items = [
                    x
                    for x in self.lessons
                    if q_l in str(x.get("text", "")).lower() or q_l in str(x.get("tags", "")).lower()
                ]
            return {"query": q, "items": items, "mock": False}

    def write_working(
        self, agent: str, session_id: str, writer: str, content: dict[str, Any], idempotency_key: str | None
    ) -> dict[str, Any]:
        with self._lock:
            if idempotency_key and idempotency_key in self._idempotency:
                return self._idempotency[idempotency_key]
            self._claim_writer(f"working:{agent}:{session_id}", writer)
            self.working.setdefault(agent, {})[session_id] = {
                "session_id": session_id,
                "agent": agent,
                "writer": writer,
                "content": content,
            }
            result = {"ok": True, "mock": False}
            if idempotency_key:
                self._idempotency[idempotency_key] = result
            return result

    def get_working(self, agent: str, session_id: str) -> dict[str, Any]:
        with self._lock:
            item = self.working.get(agent, {}).get(session_id)
            return {"agent": agent, "session_id": session_id, "item": item, "mock": False}


STORE = MemoryStore()
