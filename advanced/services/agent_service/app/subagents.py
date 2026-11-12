"""Twelve subagents: LLM ones use Composer 2.5; others are deterministic code."""

from __future__ import annotations

import os
from typing import Any

import httpx

from services.agent_service.app.llm import prompt_json

HARNESS_URL = os.getenv("HARNESS_SERVICE_URL", "http://harness:8003")
MEMORY_URL = os.getenv("MEMORY_SERVICE_URL", "http://memory_service:8005")
WANDB_MCP_URL = os.getenv("WANDB_MCP_URL", "http://wandb-mcp:8080")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")
# How many prior trials are injected into the next hypothesis / judge turn.
RECENT_EXPERIMENT_WINDOW = int(os.getenv("RECENT_EXPERIMENT_WINDOW", "5"))


def _headers() -> dict[str, str]:
    return {"X-Service-Token": SERVICE_TOKEN}


def recent_experiment_context(
    history: list[Any] | None,
    *,
    limit: int = RECENT_EXPERIMENT_WINDOW,
) -> list[dict[str, Any]]:
    """Compact view of the last N experiments for the next proposal."""
    rows: list[dict[str, Any]] = []
    for h in (history or [])[-limit:]:
        if not isinstance(h, dict):
            continue
        val = (h.get("validation_metrics") or {}).get("f1")
        train = (h.get("train_metrics") or {}).get("f1")
        rows.append(
            {
                "experiment_id": h.get("experiment_id"),
                "model_family": h.get("model_family"),
                "hyperparameters": h.get("hyperparameters"),
                "status": h.get("status"),
                "val_f1": val,
                "train_f1": train,
                "error": h.get("error"),
                "judge_action": h.get("judge_action"),
                "judge_observation": h.get("judge_observation"),
                "self_heal_attempt": h.get("self_heal_attempt"),
            }
        )
    return rows


def data_profiler(inp: dict[str, Any]) -> dict[str, Any]:
    dataset_id = inp["dataset_id"]
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            f"{HARNESS_URL}/tools/inspect_data",
            headers=_headers(),
            json={
                "session_id": inp.get("session_id", "s"),
                "dataset_id": dataset_id,
                "correlation_id": inp.get("correlation_id", "c"),
            },
        )
        r.raise_for_status()
        profile = r.json().get("profile_view") or r.json()
    return {
        "dataset_id": dataset_id,
        "n_rows": profile.get("n_rows_visible"),
        "n_columns": profile.get("n_columns"),
        "target_column": profile.get("target_column"),
        "task_type": profile.get("task_type"),
        "class_balance": profile.get("class_balance"),
        "identifier_columns": profile.get("identifier_columns", []),
        "feature_columns": profile.get("feature_columns", []),
    }


def leakage_auditor(inp: dict[str, Any]) -> dict[str, Any]:
    ids = list(inp.get("identifier_columns") or [])
    flags = [f"drop identifier column {c}" for c in ids]
    return {"leakage_flags": flags, "ok": True}


def feature_analyst(inp: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "feature_notes": [
            "Prefer tree ensembles if class imbalance is mild.",
            "Drop identifier columns before training.",
        ],
        "suggested_drops": list(inp.get("identifier_columns") or []),
    }
    payload, used = prompt_json(
        "You are a feature analyst for a tabular churn classifier.",
        f"Profile context: {inp}. Return JSON with feature_notes (string[]) and suggested_drops (string[]).",
        fallback,
    )
    payload["used_llm"] = used
    return payload


def memory_retriever(inp: dict[str, Any]) -> dict[str, Any]:
    q = inp.get("query") or "classification"
    session_id = str(inp.get("session_id") or "")
    recent = inp.get("recent_experiments")
    if not isinstance(recent, list):
        recent = recent_experiment_context(inp.get("experiment_history"))
    lessons: list[Any] = []
    findings: list[Any] = []
    session_history: list[Any] = []
    note = None
    with httpx.Client(timeout=15.0) as client:
        r = client.get(f"{MEMORY_URL}/lessons", params={"q": q}, headers=_headers())
        if r.status_code >= 400:
            note = "memory unavailable"
        else:
            lessons = r.json().get("items", [])
        if session_id:
            fr = client.get(
                f"{MEMORY_URL}/findings",
                params={"session_id": session_id},
                headers=_headers(),
            )
            if fr.status_code < 400:
                findings = (fr.json().get("items") or [])[-RECENT_EXPERIMENT_WINDOW:]
            hr = client.get(
                f"{MEMORY_URL}/history",
                params={"session_id": session_id},
                headers=_headers(),
            )
            if hr.status_code < 400:
                session_history = (hr.json().get("items") or [])[-RECENT_EXPERIMENT_WINDOW:]
    out: dict[str, Any] = {
        "lessons": lessons,
        "recent_experiments": recent,
        "findings": findings,
        "session_history": session_history,
        "window": RECENT_EXPERIMENT_WINDOW,
    }
    if note:
        out["note"] = note
    return out


def _hp_grid(family: str) -> list[dict[str, Any]]:
    """Wide enough grids that a budget-15 session rarely exhausts novelty."""
    if family == "logistic_regression":
        return [
            {"C": c, "max_iter": mi}
            for c in (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
            for mi in (150, 200, 300, 400)
        ]
    if family == "random_forest":
        return [
            {"n_estimators": ne, "max_depth": md}
            for ne in (30, 60, 90, 120, 160, 200, 250)
            for md in (2, 3, 5, 7, 9, 12, None)
        ]
    # hist_gradient_boosting and xgboost (alias) share the same HP shape.
    return [
        {"learning_rate": lr, "max_iter": mi}
        for lr in (0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2)
        for mi in (30, 50, 80, 120, 160, 200)
    ]


def hypothesis_drafter(inp: dict[str, Any]) -> dict[str, Any]:
    history = [h for h in (inp.get("experiment_history") or []) if isinstance(h, dict)]
    recent = inp.get("recent_experiments")
    if not isinstance(recent, list):
        recent = recent_experiment_context(history)
    strategy = str(inp.get("research_strategy") or "model_search")
    fixed_family = inp.get("fixed_model_family")
    families = (
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
        "xgboost",
    )
    # Prefer families that have not hard-failed; bias toward best val_f1 so far.
    # Use full history (not only the last-5 window) so we do not re-propose known failures.
    failed_families = {
        str(h.get("model_family"))
        for h in history
        if h.get("status") == "failed"
        or (isinstance(h.get("error"), str) and h.get("error"))
    }
    scored = [
        (
            float((h.get("validation_metrics") or {}).get("f1") or h.get("val_f1") or -1),
            str(h.get("model_family")),
        )
        for h in history
        if isinstance((h.get("validation_metrics") or {}).get("f1"), (int, float))
        or isinstance(h.get("val_f1"), (int, float))
    ]
    best_family = max(scored, key=lambda t: t[0])[1] if scored else None
    families_tried = {h.get("model_family") for h in history}
    n = len(history)

    if strategy == "blackbox_tuning" and fixed_family:
        # Fixed model upfront — only search hyperparameters.
        preferred = str(fixed_family)
    else:
        preferred = next((f for f in families if f not in families_tried), None)
        if preferred is None:
            # All families tried — lean on best scorer, else rotate, skip chronic failures.
            candidates = [f for f in families if f not in failed_families] or list(families)
            if best_family in candidates:
                preferred = best_family
            else:
                preferred = candidates[n % len(candidates)]
        elif preferred in failed_families and best_family and best_family not in failed_families:
            preferred = best_family

    # Novelty vs full history for this family (recent-only caused budget-15 duplicate burn).
    seen_hp = {
        tuple(sorted((h.get("hyperparameters") or {}).items()))
        for h in history
        if h.get("model_family") == preferred
    }
    hp_options = _hp_grid(preferred)
    hp = next((opt for opt in hp_options if tuple(sorted(opt.items())) not in seen_hp), None)
    if hp is None and strategy != "blackbox_tuning":
        # Exhausted this family — try another unused combo across families.
        for fam in families:
            if fam in failed_families and fam != preferred:
                continue
            seen = {
                tuple(sorted((h.get("hyperparameters") or {}).items()))
                for h in history
                if h.get("model_family") == fam
            }
            cand = next((opt for opt in _hp_grid(fam) if tuple(sorted(opt.items())) not in seen), None)
            if cand is not None:
                preferred = fam
                hp = cand
                break
    if hp is None:
        # Last resort: mutate with a unique suffix value.
        if strategy == "blackbox_tuning" and fixed_family:
            preferred = str(fixed_family)
        else:
            preferred = best_family or preferred
        hp = {"C": 1.0 + 0.01 * (n + 1), "max_iter": 200 + n}
        if preferred == "random_forest":
            hp = {"n_estimators": 50 + n * 7, "max_depth": 3 + (n % 8)}
        elif preferred in {"hist_gradient_boosting", "xgboost"}:
            hp = {"learning_rate": round(0.02 + 0.01 * (n % 15), 3), "max_iter": 40 + n * 5}

    prior_bits = []
    for h in recent:
        if not isinstance(h, dict):
            continue
        bit = f"{h.get('model_family')} val_f1={h.get('val_f1')}"
        if h.get("status") == "failed":
            bit += f" FAILED({str(h.get('error') or '')[:60]})"
        if h.get("judge_action"):
            bit += f" judge={h.get('judge_action')}"
        prior_bits.append(bit)
    prior_summary = "; ".join(prior_bits) if prior_bits else "none yet"
    mode_note = (
        f"blackbox HP tuning on fixed model {preferred}"
        if strategy == "blackbox_tuning"
        else "free model search under budget"
    )
    fallback = {
        "model_family": preferred,
        "hyperparameters": hp,
        "rationale": (
            f"Trial #{n + 1} ({mode_note}): propose {preferred} informed by last "
            f"{len(recent)} experiments [{prior_summary}]."
        ),
        "prior_experiments_considered": len(recent),
        "research_strategy": strategy,
    }
    system = (
        "You draft ONE experiment hypothesis for tabular binary classification. "
        "Never invent new model code. Use recent_experiments to avoid repeats."
    )
    if strategy == "blackbox_tuning" and fixed_family:
        system += (
            f" Strategy=blackbox_tuning: model_family MUST stay {fixed_family}; "
            "only vary hyperparameters."
        )
    else:
        system += (
            " Strategy=model_search: choose any allowed family "
            "(logistic_regression, random_forest, hist_gradient_boosting, xgboost) "
            "and hyperparameters to maximize score under budget."
        )
    payload, used = prompt_json(
        system,
        f"Context: { {**inp, 'recent_experiments': recent} }. "
        "Return JSON: model_family, hyperparameters, rationale.",
        fallback,
    )
    if strategy == "blackbox_tuning" and fixed_family:
        payload["model_family"] = fixed_family
    payload["used_llm"] = used
    payload["prior_experiments_considered"] = len(recent)
    payload["recent_experiments"] = recent
    payload["research_strategy"] = strategy
    return payload


def novelty_checker(inp: dict[str, Any]) -> dict[str, Any]:
    proposed = inp.get("proposed") or {}
    history = inp.get("experiment_history") or []
    for h in history:
        if (
            h.get("model_family") == proposed.get("model_family")
            and h.get("hyperparameters") == proposed.get("hyperparameters")
        ):
            return {"novelty_ok": False, "reason": "duplicate of prior experiment"}
    return {"novelty_ok": True, "reason": "new combination"}


def config_validator(inp: dict[str, Any]) -> dict[str, Any]:
    spec = inp.get("experiment_spec") or inp.get("proposed") or {}
    with httpx.Client(timeout=15.0) as client:
        r = client.post(
            f"{HARNESS_URL}/tools/validate_experiment",
            headers=_headers(),
            json={
                "session_id": inp.get("session_id", "s"),
                "correlation_id": inp.get("correlation_id", "c"),
                "experiment_spec": spec,
            },
        )
        r.raise_for_status()
        return r.json()


def experiment_runner(inp: dict[str, Any]) -> dict[str, Any]:
    spec = dict(inp.get("experiment_spec") or {})
    spec.setdefault("dataset_id", inp.get("dataset_id"))
    spec.setdefault("target_column", inp.get("target_column"))
    with httpx.Client(timeout=180.0) as client:
        r = client.post(
            f"{HARNESS_URL}/tools/run_experiment",
            headers=_headers(),
            json={
                "session_id": inp["session_id"],
                "correlation_id": inp.get("correlation_id", "c"),
                "idempotency_key": inp["idempotency_key"],
                "experiment_spec": spec,
            },
        )
        r.raise_for_status()
        return r.json()


def error_repair(inp: dict[str, Any]) -> dict[str, Any]:
    error = str(inp.get("error") or "")
    spec = dict(inp.get("experiment_spec") or {})
    hp = dict(spec.get("hyperparameters") or {})
    if "max_depth" in error.lower():
        hp["max_depth"] = 4
        return {"repaired": True, "experiment_spec": {**spec, "hyperparameters": hp}, "note": "fixed max_depth"}
    if "not allowed" in error.lower():
        return {
            "repaired": True,
            "experiment_spec": {
                **spec,
                "model_family": "logistic_regression",
                "hyperparameters": {"C": 1.0, "max_iter": 200},
            },
            "note": "fell back to logistic_regression",
        }
    return {"repaired": False, "experiment_spec": spec, "note": "no automatic repair"}


def metric_analyst(inp: dict[str, Any]) -> dict[str, Any]:
    result = inp.get("result") or {}
    val = (result.get("validation_metrics") or {}).get("f1")
    train = (result.get("train_metrics") or {}).get("f1")
    fallback = {
        "observation": f"validation f1={val}, train f1={train}",
        "gap": None if val is None or train is None else float(train) - float(val),
    }
    payload, used = prompt_json(
        "You are a metric analyst. Be concise.",
        f"Result: {result}. Return JSON with observation (string) and gap (number|null).",
        fallback,
    )
    payload["used_llm"] = used
    return payload


def overfitting_checker(inp: dict[str, Any]) -> dict[str, Any]:
    gap = inp.get("gap")
    if gap is None:
        train = ((inp.get("result") or {}).get("train_metrics") or {}).get("f1")
        val = ((inp.get("result") or {}).get("validation_metrics") or {}).get("f1")
        if train is not None and val is not None:
            gap = float(train) - float(val)
    risk = "high" if gap is not None and gap > 0.15 else "low"
    return {"overfitting_risk": risk, "gap": gap}


def independent_reviewer(inp: dict[str, Any]) -> dict[str, Any]:
    result = inp.get("result") or {}
    target = float(inp.get("target_score") or 0.75)
    val = float(((result.get("validation_metrics") or {}).get("f1") or 0.0))
    budget_left = int(inp.get("budget_left") or 0)
    recent = inp.get("recent_experiments")
    if not isinstance(recent, list):
        recent = recent_experiment_context(inp.get("experiment_history"))
    if val >= target:
        action = "accept"
    elif budget_left <= 0:
        action = "stop"
    elif result.get("status") != "succeeded":
        action = "reject"
    else:
        action = "revise"
    best_prior = None
    for h in recent:
        if isinstance(h, dict) and isinstance(h.get("val_f1"), (int, float)):
            if best_prior is None or float(h["val_f1"]) > best_prior:
                best_prior = float(h["val_f1"])
    fallback = {
        "action": action,
        "observation": f"val_f1={val} target={target}"
        + (f" best_prior={best_prior}" if best_prior is not None else ""),
        "hypothesis": "Adjust capacity or regularization on next trial.",
        "next_action": "propose next experiment" if action == "revise" else action,
        "prior_experiments_considered": len(recent),
    }
    payload, used = prompt_json(
        "You are an independent ML judge. Choose action in {revise,reject,accept,stop}. "
        "Use recent_experiments (last up to 5) for trend context.",
        f"Context: { {**inp, 'recent_experiments': recent} }. "
        "Return JSON: action, observation, hypothesis, next_action.",
        fallback,
    )
    if payload.get("action") not in {"revise", "reject", "accept", "stop"}:
        payload["action"] = action
    # Keep loop progressing under budget when score is below target (LLM cannot short-circuit).
    if budget_left > 0 and val < target and payload.get("action") in {"accept", "stop"}:
        payload["action"] = "revise"
        payload["next_action"] = "propose next experiment"
        payload["note"] = "overrode early accept/stop while budget remains"
    # A failed trial is rejected as a candidate, but the session should still
    # spend remaining budget on a different proposal.
    if (
        budget_left > 0
        and result.get("status") != "succeeded"
        and payload.get("action") == "reject"
    ):
        payload["next_action"] = "propose next experiment"
        payload["note"] = "rejected this trial; continue under remaining budget"
    payload["used_llm"] = used
    payload["prior_experiments_considered"] = len(recent)
    payload["recent_experiments"] = recent
    return payload


def query_wandb_readonly(inp: dict[str, Any]) -> dict[str, Any]:
    """Read-only W&B MCP allow-list. Filters out runs tagged final."""
    try:
        with httpx.Client(timeout=10.0) as client:
            # Soft probe — wandb-mcp may be down; never hard-fail the loop.
            r = client.get(f"{WANDB_MCP_URL}/health", headers=_headers())
            if r.status_code >= 400:
                return {"status": "wandb_unavailable", "runs": []}
    except Exception:  # noqa: BLE001
        return {"status": "wandb_unavailable", "runs": []}
    # Real MCP tool calls would go here; for teaching we return empty filtered set.
    return {"status": "ok", "runs": [], "note": "filtered out tag=final; allow-list only"}


HANDLERS = {
    "data_profiler": data_profiler,
    "leakage_auditor": leakage_auditor,
    "feature_analyst": feature_analyst,
    "memory_retriever": memory_retriever,
    "hypothesis_drafter": hypothesis_drafter,
    "novelty_checker": novelty_checker,
    "config_validator": config_validator,
    "experiment_runner": experiment_runner,
    "error_repair": error_repair,
    "metric_analyst": metric_analyst,
    "overfitting_checker": overfitting_checker,
    "independent_reviewer": independent_reviewer,
}
