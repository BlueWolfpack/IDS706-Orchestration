"""Cursor Composer 2.5 via Agent SDK. Deterministic fallback when key/SDK missing."""

from __future__ import annotations

import json
import os
import re
from typing import Any

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cursor")
LLM_MODEL = os.getenv("LLM_MODEL", "composer-2.5")
CURSOR_API_KEY = os.getenv("CURSOR_API_KEY", "")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group(0))
        raise


def prompt_json(system: str, user: str, fallback: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return (payload, used_llm). Falls back if Cursor SDK/key unavailable."""
    # Prefer fast deterministic path when disabled (keeps live SSE responsive).
    if os.getenv("AGENT_LLM_ENABLED", "true").lower() in {"0", "false", "no"}:
        return fallback, False
    if LLM_PROVIDER != "cursor" or not CURSOR_API_KEY:
        return fallback, False
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        result = Agent.prompt(
            f"{system}\n\nRespond with ONLY a JSON object.\n\n{user}",
            AgentOptions(
                api_key=CURSOR_API_KEY,
                model=LLM_MODEL,
                local=LocalAgentOptions(cwd=os.getcwd()),
            ),
        )
        text = getattr(result, "result", None) or str(result)
        return _extract_json(str(text)), True
    except Exception:  # noqa: BLE001 — teaching demo must not die without LLM
        return fallback, False
