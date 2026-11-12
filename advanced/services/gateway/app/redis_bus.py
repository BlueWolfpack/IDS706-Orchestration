"""Redis Streams fan-in for live session events (Stage C7)."""

from __future__ import annotations

import json
import os
from typing import Any

import redis.asyncio as redis

from contracts import EventEnvelope

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STREAM_PREFIX = "automl:session:"


def stream_key(session_id: str) -> str:
    return f"{STREAM_PREFIX}{session_id}:events"


class RedisEventBus:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None
        self._available = False

    async def connect(self) -> bool:
        if self._client is not None and self._available:
            return True
        try:
            self._client = redis.from_url(REDIS_URL, decode_responses=True)
            await self._client.ping()
            self._available = True
            return True
        except Exception:  # noqa: BLE001 — fall back to in-memory only
            self._client = None
            self._available = False
            return False

    @property
    def available(self) -> bool:
        return self._available

    async def publish(self, session_id: str, event: EventEnvelope) -> str | None:
        if not await self.connect() or self._client is None:
            return None
        payload = event.model_dump(mode="json")
        return await self._client.xadd(
            stream_key(session_id),
            {"data": json.dumps(payload)},
            maxlen=5000,
            approximate=True,
        )

    async def stream_exists(self, session_id: str) -> bool:
        if not await self.connect() or self._client is None:
            return False
        try:
            return bool(await self._client.exists(stream_key(session_id)))
        except Exception:  # noqa: BLE001
            return False

    async def xread_once(
        self, session_id: str, last_id: str = "0-0", block_ms: int = 2000, count: int = 50
    ) -> list[tuple[str, EventEnvelope]]:
        """Blocking read of new messages after last_id. Empty list on timeout."""
        if not await self.connect() or self._client is None:
            return []
        rows = await self._client.xread(
            {stream_key(session_id): last_id}, count=count, block=block_ms
        )
        out: list[tuple[str, EventEnvelope]] = []
        if not rows:
            return out
        for _stream, messages in rows:
            for msg_id, fields in messages:
                raw = fields.get("data") or "{}"
                try:
                    envelope = EventEnvelope.model_validate(json.loads(raw))
                except Exception:  # noqa: BLE001
                    continue
                out.append((msg_id, envelope))
        return out


bus = RedisEventBus()


def bus_status() -> dict[str, Any]:
    return {"redis_url": REDIS_URL, "available": bus.available}
