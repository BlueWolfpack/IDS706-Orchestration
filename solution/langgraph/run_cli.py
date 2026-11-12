#!/usr/bin/env python3
"""CLI entry for the solution research loop (JSON out)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))

from solution.langgraph.graph import run_solution_loop  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Solution research loop (LangGraph)")
    p.add_argument(
        "--dataset",
        default=str(REPO / "datasets" / "Titanic-Dataset.csv"),
    )
    p.add_argument("--target", default="Survived")
    p.add_argument("--target-score", type=float, default=0.8)
    p.add_argument("--max-cycles", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    result = run_solution_loop(
        dataset_path=args.dataset,
        target_column=args.target,
        target_score=args.target_score,
        max_cycles=args.max_cycles,
        seed=args.seed,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
