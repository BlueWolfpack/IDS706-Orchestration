#!/usr/bin/env python3
"""Equal-budget evaluation: A baseline, B random search, C single planner, D multi-agent.

Prints validation/holdout scores, experiment count, time. Does not claim a winner
unless the numbers show it.
"""

from __future__ import annotations

import argparse
import random
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "datasets" / "churn_sample.csv"
BUDGET = 5
FAMILIES = [
    ("logistic_regression", {"C": 1.0, "max_iter": 200}),
    ("random_forest", {"n_estimators": 40, "max_depth": 4}),
    ("hist_gradient_boosting", {"learning_rate": 0.1, "max_iter": 50}),
]


def upload(client: httpx.Client, dataset_url: str, token: str) -> str:
    r = client.post(
        f"{dataset_url}/datasets",
        headers={"X-Service-Token": token},
        files={"file": ("churn_sample.csv", SAMPLE.read_bytes(), "text/csv")},
        data={"target_column": "churned", "task_type": "classification"},
    )
    r.raise_for_status()
    return r.json()["dataset_id"]


def run_one(client: httpx.Client, harness: str, token: str, dataset_id: str, family: str, hp: dict) -> dict:
    eid = f"e-{uuid.uuid4().hex[:8]}"
    r = client.post(
        f"{harness}/tools/run_experiment",
        headers={"X-Service-Token": token},
        json={
            "session_id": "eval",
            "correlation_id": eid,
            "idempotency_key": eid,
            "experiment_spec": {
                "experiment_id": eid,
                "dataset_id": dataset_id,
                "target_column": "churned",
                "model_family": family,
                "hyperparameters": hp,
            },
        },
    )
    r.raise_for_status()
    return r.json()


def holdout(client: httpx.Client, dataset_url: str, token: str, dataset_id: str, model_ref: str) -> float | None:
    r = client.post(
        f"{dataset_url}/internal/holdout/evaluate",
        headers={"X-Service-Token": token, "X-Harness-Token": token},
        json={
            "session_id": f"eval-{uuid.uuid4().hex[:6]}",
            "dataset_id": dataset_id,
            "model_ref": model_ref,
            "metric": "f1",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    if r.status_code >= 400:
        return None
    return float(r.json()["score"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--harness", default="http://127.0.0.1:8003")
    p.add_argument("--dataset", default="http://127.0.0.1:8004")
    p.add_argument("--orchestrator", default="http://127.0.0.1:8011")
    p.add_argument("--token", default="dev-service-token")
    args = p.parse_args()

    with httpx.Client(timeout=180.0) as client:
        ds = upload(client, args.dataset, args.token)
        rows = []

        # A — fixed logistic baseline (1 trial)
        t0 = time.perf_counter()
        a = run_one(client, args.harness, args.token, ds, *FAMILIES[0])
        rows.append(("A_baseline", 1, a, time.perf_counter() - t0))

        # B — random search for BUDGET trials
        t0 = time.perf_counter()
        best_b = None
        for _ in range(BUDGET):
            family, base_hp = random.choice(FAMILIES)
            hp = dict(base_hp)
            if "C" in hp:
                hp["C"] = random.choice([0.5, 1.0, 2.0])
            if "n_estimators" in hp:
                hp["n_estimators"] = random.choice([20, 40, 80])
            if "learning_rate" in hp:
                hp["learning_rate"] = random.choice([0.05, 0.1, 0.2])
            r = run_one(client, args.harness, args.token, ds, family, hp)
            if best_b is None or (r.get("validation_metrics") or {}).get("f1", -1) > (
                best_b.get("validation_metrics") or {}
            ).get("f1", -1):
                best_b = r
        rows.append(("B_random", BUDGET, best_b, time.perf_counter() - t0))

        # C — single planner: always HGB then RF then LR
        t0 = time.perf_counter()
        best_c = None
        for family, hp in FAMILIES[:BUDGET]:
            r = run_one(client, args.harness, args.token, ds, family, hp)
            if best_c is None or (r.get("validation_metrics") or {}).get("f1", -1) > (
                best_c.get("validation_metrics") or {}
            ).get("f1", -1):
                best_c = r
        rows.append(("C_single_planner", min(BUDGET, len(FAMILIES)), best_c, time.perf_counter() - t0))

        # D — multi-agent via orchestrator
        t0 = time.perf_counter()
        d_body = None
        try:
            resp = client.post(
                f"{args.orchestrator}/runs",
                headers={"X-Service-Token": args.token},
                json={
                    "dataset_id": ds,
                    "target_column": "churned",
                    "experiment_budget": BUDGET,
                    "target_score": 0.99,
                },
            )
            resp.raise_for_status()
            d_body = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"D_multi_agent failed: {exc}")
        rows.append(("D_multi_agent", BUDGET, d_body, time.perf_counter() - t0))

        print("method\ttrials\tval_f1\tholdout_f1\tseconds")
        for name, trials, payload, secs in rows:
            if payload is None:
                print(f"{name}\t{trials}\tn/a\tn/a\t{secs:.1f}")
                continue
            if name.startswith("D_"):
                state = payload.get("state") or {}
                val = state.get("best_val_score")
                hold = state.get("holdout_score")
                print(f"{name}\t{state.get('experiment_count', trials)}\t{val}\t{hold}\t{secs:.1f}")
            else:
                val = (payload.get("validation_metrics") or {}).get("f1")
                hold = holdout(client, args.dataset, args.token, ds, payload.get("model_ref") or "")
                print(f"{name}\t{trials}\t{val}\t{hold}\t{secs:.1f}")


if __name__ == "__main__":
    main()
