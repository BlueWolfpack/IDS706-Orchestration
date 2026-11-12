"""Probe sibling /healthz endpoints for the Control Center health strip."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

SERVICE_URLS: dict[str, str] = {
    "gateway": os.getenv("GATEWAY_SELF_URL", "http://127.0.0.1:8000"),
    "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8001"),
    "agent_service": os.getenv("AGENT_SERVICE_URL", "http://agent_service:8002"),
    "harness": os.getenv("HARNESS_SERVICE_URL", "http://harness:8003"),
    "dataset_service": os.getenv("DATASET_SERVICE_URL", "http://dataset_service:8004"),
    "memory_service": os.getenv("MEMORY_SERVICE_URL", "http://memory_service:8005"),
    "tracking_service": os.getenv("TRACKING_SERVICE_URL", "http://tracking_service:8006"),
}


async def _one(client: httpx.AsyncClient, name: str, base: str) -> tuple[str, str]:
    try:
        r = await client.get(f"{base.rstrip('/')}/healthz")
        if r.status_code < 400:
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            status = str(body.get("status") or "ok")
            return name, "ok" if status == "ok" else status
        return name, "down"
    except Exception:  # noqa: BLE001
        return name, "down"


async def probe_services() -> dict[str, str]:
    timeout = httpx.Timeout(2.5, connect=1.5)
    async with httpx.AsyncClient(timeout=timeout) as client:
        pairs = await asyncio.gather(
            *[_one(client, name, url) for name, url in SERVICE_URLS.items()]
        )
    return dict(pairs)


async def probe_payload() -> dict[str, Any]:
    services = await probe_services()
    down = [n for n, s in services.items() if s != "ok"]
    note = "all services reachable" if not down else f"down: {', '.join(down)}"
    return {"services": services, "note": note}
