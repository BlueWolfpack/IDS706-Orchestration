"""Load timed mock event scenarios. Every event is sample data with mock=true."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).resolve().parent

SCENARIO_NAMES = (
    "happy",
    "revise_loop",
    "repair",
    "terminal_failure",
    "budget_stop",
    "service_down",
)


def load_scenario(name: str) -> list[dict[str, Any]]:
    if name not in SCENARIO_NAMES:
        raise ValueError(f"unknown scenario {name!r}; choose one of {SCENARIO_NAMES}")
    path = FIXTURES_DIR / f"{name}.json"
    data = json.loads(path.read_text())
    steps = data["steps"]
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"scenario {name} has no steps")
    return steps
