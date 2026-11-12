"""Unit tests for loop run history store."""

from __future__ import annotations

from pathlib import Path

from services.gateway.app.loop_runs import MAX_RUNS, LoopRunStore


def test_append_list_get_and_cap(tmp_path: Path) -> None:
    path = tmp_path / "runs.json"
    store = LoopRunStore(path=path)

    first = store.append(
        {
            "dataset": "a.csv",
            "target_column": "y",
            "target_score": 0.8,
            "max_cycles": 3,
            "cycles": 1,
            "best_val_f1": 0.5,
            "status": "completed",
        }
    )
    assert first["run_id"].startswith("slr_")
    assert store.get(first["run_id"])["dataset"] == "a.csv"

    for i in range(MAX_RUNS + 5):
        store.append({"dataset": f"d{i}.csv", "target_column": "y", "status": "completed"})

    rows = store.list_runs()
    assert len(rows) == MAX_RUNS
    # Newest first
    assert rows[0]["dataset"] == f"d{MAX_RUNS + 4}.csv"

    # Reload from disk
    again = LoopRunStore(path=path)
    assert len(again.list_runs()) == MAX_RUNS
    assert again.get(first["run_id"]) is None  # aged out of the cap


def test_error_record(tmp_path: Path) -> None:
    store = LoopRunStore(path=tmp_path / "runs.json")
    row = store.append(
        {
            "dataset": "x.csv",
            "target_column": "t",
            "status": "error",
            "error": "boom",
        }
    )
    assert row["status"] == "error"
    assert row["error"] == "boom"
