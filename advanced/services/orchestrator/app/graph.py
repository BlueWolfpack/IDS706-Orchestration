"""Deterministic LangGraph meta-supervisor. Emits live Redis events; no LLM here."""

from __future__ import annotations

import os
import uuid
from typing import Any, TypedDict

import httpx
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from contracts import EventType
from services.orchestrator.app.events import emit

AGENT_URL = os.getenv("AGENT_SERVICE_URL", "http://agent_service:8002")
TRACKING_URL = os.getenv("TRACKING_SERVICE_URL", "http://tracking_service:8006")
MEMORY_URL = os.getenv("MEMORY_SERVICE_URL", "http://memory_service:8005")
DATASET_URL = os.getenv("DATASET_SERVICE_URL", "http://dataset_service:8004")
SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "dev-service-token")
HARNESS_TOKEN = os.getenv("HARNESS_TOKEN", SERVICE_TOKEN)
# Per-experiment bounded repair attempts (validate/run → repair → retry).
SELF_HEAL_BUDGET = int(os.getenv("SELF_HEAL_BUDGET", "3"))
# Prior trials injected into the next hypothesize / judge turn.
RECENT_EXPERIMENT_WINDOW = int(os.getenv("RECENT_EXPERIMENT_WINDOW", "5"))


def _recent_experiments(history: list[Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for h in (history or [])[-RECENT_EXPERIMENT_WINDOW:]:
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


class ResearchStateDict(TypedDict, total=False):
    session_id: str
    dataset_id: str
    target_column: str
    task_type: str
    metric: str
    target_score: float
    experiment_budget: int
    research_strategy: str
    fixed_model_family: str
    per_trial_timeout_seconds: int
    data_profile: dict
    proposed_experiment: dict
    experiment_history: list
    latest_result: dict
    judge_verdict: dict
    best_experiment_id: str
    best_val_score: float
    experiment_count: int
    retry_count: int
    status: str
    stop_reason: str
    model_ref: str
    holdout_score: float


def _headers() -> dict[str, str]:
    return {"X-Service-Token": SERVICE_TOKEN}


def _invoke(
    lead: str,
    subagent: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    experiment_id: str | None = None,
    extra_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cid = str(uuid.uuid4())
    exp_id = experiment_id or (payload.get("experiment_spec") or {}).get("experiment_id")
    started_payload: dict[str, Any] = {"lead": lead, "subagent": subagent}
    if exp_id:
        started_payload["experiment_id"] = exp_id
    if extra_event:
        started_payload.update(extra_event)
    emit(
        session_id,
        EventType.AGENT_STARTED,
        started_payload,
        source_service="agent_service",
        source_agent=subagent,
        correlation_id=cid,
    )
    # Trial lifecycle for the runner
    if subagent == "experiment_runner":
        trial_start: dict[str, Any] = {
            "experiment_id": exp_id,
            "model_family": (payload.get("experiment_spec") or {}).get("model_family"),
        }
        if extra_event:
            trial_start.update(extra_event)
        emit(
            session_id,
            EventType.TRIAL_STARTED,
            trial_start,
            source_service="harness",
            source_agent=subagent,
            correlation_id=cid,
        )
    try:
        with httpx.Client(timeout=180.0) as client:
            r = client.post(
                f"{AGENT_URL}/agents/{lead}/{subagent}/invoke",
                headers=_headers(),
                json={
                    "session_id": session_id,
                    "correlation_id": cid,
                    "lead": lead,
                    "subagent": subagent,
                    "input": payload,
                },
            )
            r.raise_for_status()
            out = r.json().get("output") or {}
    except Exception as exc:  # noqa: BLE001
        emit(
            session_id,
            EventType.SERVICE_ERROR,
            {"lead": lead, "subagent": subagent, "error": str(exc)},
            source_service="agent_service",
            source_agent=subagent,
            correlation_id=cid,
        )
        if subagent == "experiment_runner":
            emit(
                session_id,
                EventType.TRIAL_FAILED,
                {"error": str(exc), "status": "failed"},
                source_service="harness",
                source_agent=subagent,
                correlation_id=cid,
            )
        raise

    completed_payload: dict[str, Any] = {
        "lead": lead,
        "subagent": subagent,
        "summary": _summary(subagent, out),
        "output": out,
    }
    if exp_id:
        completed_payload["experiment_id"] = exp_id
    if extra_event:
        completed_payload.update(extra_event)
    emit(
        session_id,
        EventType.AGENT_COMPLETED,
        completed_payload,
        source_service="agent_service",
        source_agent=subagent,
        correlation_id=cid,
    )
    if subagent == "experiment_runner":
        et = EventType.TRIAL_COMPLETED if out.get("status") == "succeeded" else EventType.TRIAL_FAILED
        trial_payload = dict(out)
        # Prefer the orchestrator's experiment id so trial_* and agent_* share one key.
        if exp_id:
            trial_payload["experiment_id"] = exp_id
        if extra_event:
            trial_payload.update(extra_event)
        emit(
            session_id,
            et,
            trial_payload,  
            source_service="harness",
            source_agent=subagent,
            correlation_id=cid,
        )
    if subagent == "independent_reviewer":
        verdict_payload = dict(out)
        if exp_id:
            verdict_payload["experiment_id"] = exp_id
        emit(
            session_id,
            EventType.VERDICT_ISSUED,
            verdict_payload,
            source_service="agent_service",
            source_agent=subagent,
            correlation_id=cid,
        )
    return out


def _summary(subagent: str, out: dict[str, Any]) -> dict[str, Any]:
    if subagent == "data_profiler":
        return {
            "n_rows": out.get("n_rows"),
            "target_column": out.get("target_column"),
            "n_columns": out.get("n_columns"),
        }
    if subagent == "hypothesis_drafter":
        return {"model_family": out.get("model_family"), "rationale": out.get("rationale")}
    if subagent == "experiment_runner":
        return {
            "experiment_id": out.get("experiment_id"),
            "status": out.get("status"),
            "validation_metrics": out.get("validation_metrics"),
        }
    if subagent == "independent_reviewer":
        return {"action": out.get("action")}
    return {k: out[k] for k in list(out)[:6]}


def _with_lead(sid: str, lead: str, body):
    """Emit lead agent_started/completed around a phase so the live graph lights up."""
    cid = str(uuid.uuid4())
    emit(
        sid,
        EventType.AGENT_STARTED,
        {"lead": lead},
        source_service="orchestrator",
        source_agent=lead,
        correlation_id=cid,
    )
    try:
        out = body()
    except Exception as exc:  # noqa: BLE001
        emit(
            sid,
            EventType.AGENT_COMPLETED,
            {"lead": lead, "status": "failed", "error": str(exc)},
            source_service="orchestrator",
            source_agent=lead,
            correlation_id=cid,
        )
        raise
    emit(
        sid,
        EventType.AGENT_COMPLETED,
        {"lead": lead},
        source_service="orchestrator",
        source_agent=lead,
        correlation_id=cid,
    )
    return out


def node_profile(state: ResearchStateDict) -> ResearchStateDict:
    sid = state["session_id"]
    emit(
        sid,
        EventType.AGENT_STARTED,
        {"lead": "meta_supervisor"},
        source_service="orchestrator",
        source_agent="meta_supervisor",
    )
    emit(sid, EventType.ACTIVITY, {"message": "profiling dataset"}, source_agent="meta_supervisor")

    def _body() -> ResearchStateDict:
        profile = _invoke(
            "data_scientist",
            "data_profiler",
            sid,
            {"dataset_id": state["dataset_id"], "session_id": sid},
        )
        leak = _invoke(
            "data_scientist",
            "leakage_auditor",
            sid,
            {"identifier_columns": profile.get("identifier_columns", [])},
        )
        feats = _invoke(
            "data_scientist",
            "feature_analyst",
            sid,
            {**profile, "identifier_columns": profile.get("identifier_columns", [])},
        )
        profile["leakage_flags"] = leak.get("leakage_flags", [])
        profile["feature_notes"] = feats.get("feature_notes", [])
        return {"data_profile": profile, "status": "profiling_done"}

    return _with_lead(sid, "data_scientist", _body)


def node_hypothesize(state: ResearchStateDict) -> ResearchStateDict:
    sid = state["session_id"]
    # Allocate experiment id first so hypothesis + ML + judge events share one trail.
    exp_id = f"e-{uuid.uuid4().hex[:8]}"
    history = list(state.get("experiment_history") or [])
    recent = _recent_experiments(history)

    def _body() -> ResearchStateDict:
        emit(
            sid,
            EventType.ACTIVITY,
            {
                "kind": "experiment_context",
                "message": (
                    f"passing {len(recent)} prior experiment(s) into next proposal "
                    f"(window={RECENT_EXPERIMENT_WINDOW})"
                ),
                "experiment_id": exp_id,
                "recent_experiments": recent,
                "window": RECENT_EXPERIMENT_WINDOW,
            },
            source_service="orchestrator",
            source_agent="hypothesis_generator",
        )
        strategy = str(state.get("research_strategy") or "model_search")
        fixed_family = state.get("fixed_model_family")
        trial_timeout = int(state.get("per_trial_timeout_seconds") or 120)
        memory = _invoke(
            "hypothesis_generator",
            "memory_retriever",
            sid,
            {
                "session_id": sid,
                "data_profile": state.get("data_profile"),
                "experiment_history": history,
                "recent_experiments": recent,
                "research_strategy": strategy,
                "fixed_model_family": fixed_family,
            },
            experiment_id=exp_id,
        )
        drafted = _invoke(
            "hypothesis_generator",
            "hypothesis_drafter",
            sid,
            {
                "data_profile": state.get("data_profile"),
                "experiment_history": history,
                "recent_experiments": recent,
                "memory": memory,
                "research_strategy": strategy,
                "fixed_model_family": fixed_family,
            },
            experiment_id=exp_id,
        )
        family = drafted.get("model_family", "logistic_regression")
        if strategy == "blackbox_tuning" and fixed_family:
            family = fixed_family
        proposed = {
            "experiment_id": exp_id,
            "session_id": sid,
            "dataset_id": state["dataset_id"],
            "target_column": state["target_column"],
            "model_family": family,
            "hyperparameters": drafted.get("hyperparameters") or {"C": 1.0, "max_iter": 200},
            "rationale": drafted.get("rationale", ""),
            "prior_experiments_considered": drafted.get(
                "prior_experiments_considered", len(recent)
            ),
            "research_strategy": strategy,
            "timeout_seconds": trial_timeout,
        }
        novelty = _invoke(
            "hypothesis_generator",
            "novelty_checker",
            sid,
            {
                "proposed": proposed,
                "experiment_history": history,
                "recent_experiments": recent,
            },
            experiment_id=exp_id,
        )
        proposed["novelty_ok"] = bool(novelty.get("novelty_ok", True))
        return {"proposed_experiment": proposed}

    return _with_lead(sid, "hypothesis_generator", _body)


def node_run(state: ResearchStateDict) -> ResearchStateDict:
    sid = state["session_id"]
    proposed = dict(state.get("proposed_experiment") or {})
    if not proposed.get("novelty_ok", True):
        exp_blocked = str(proposed.get("experiment_id") or "")
        emit(
            sid,
            EventType.ACTIVITY,
            {
                "message": "duplicate experiment blocked",
                "experiment_id": exp_blocked,
                "model_family": proposed.get("model_family"),
            },
            source_agent="novelty_checker",
        )
        # Surface blocked proposals on the timeline/chart (no val score).
        emit(
            sid,
            EventType.TRIAL_STARTED,
            {
                "experiment_id": exp_blocked,
                "model_family": proposed.get("model_family"),
                "blocked": True,
            },
            source_service="orchestrator",
            source_agent="novelty_checker",
        )
        emit(
            sid,
            EventType.TRIAL_FAILED,
            {
                "experiment_id": exp_blocked,
                "status": "failed",
                "reason": "duplicate experiment blocked",
                "error": "duplicate experiment blocked",
                "model_family": proposed.get("model_family"),
                "blocked": True,
                "validation_metrics": {},
            },
            source_service="orchestrator",
            source_agent="novelty_checker",
        )
        # Count blocked proposals toward the budget so we cannot loop forever.
        count = int(state.get("experiment_count") or 0) + 1
        budget = int(state.get("experiment_budget") or 10)
        history = list(state.get("experiment_history") or [])
        history.append(
            {
                "experiment_id": exp_blocked,
                "status": "failed",
                "error": "duplicate experiment blocked",
                "model_family": proposed.get("model_family"),
                "hyperparameters": proposed.get("hyperparameters"),
                "validation_metrics": {},
                "train_metrics": {},
                "judge_action": "revise" if count < budget else "stop",
                "judge_observation": "duplicate blocked",
            }
        )
        emit(
            sid,
            EventType.BUDGET_UPDATE,
            {
                "experiment_count": count,
                "experiment_budget": budget,
                "best_val_score": state.get("best_val_score"),
                "experiment_id": exp_blocked,
            },
        )
        action = "stop" if count >= budget else "revise"
        return {
            "latest_result": {
                "experiment_id": exp_blocked,
                "status": "failed",
                "error": "duplicate experiment blocked",
                "validation_metrics": {},
                "train_metrics": {},
            },
            "experiment_history": history,
            "experiment_count": count,
            "judge_verdict": {
                "action": action,
                "observation": "duplicate blocked",
                "next_action": action,
            },
        }

    exp_id = str(proposed.get("experiment_id") or "")

    def _emit_heal(
        *,
        attempt: int,
        trigger: str,
        error: str | None,
        repaired: bool | None = None,
        note: str | None = None,
        exhausted: bool = False,
    ) -> None:
        payload: dict[str, Any] = {
            "kind": "self_heal",
            "message": (
                f"self-heal {attempt}/{SELF_HEAL_BUDGET}"
                + (f" · {trigger}" if trigger else "")
                + (" · exhausted" if exhausted else "")
            ),
            "experiment_id": exp_id or proposed.get("experiment_id"),
            "self_heal_attempt": attempt,
            "self_heal_budget": SELF_HEAL_BUDGET,
            "retry_count": attempt,
            "trigger": trigger,
            "error": error,
            "exhausted": exhausted,
        }
        if repaired is not None:
            payload["repaired"] = repaired
        if note:
            payload["note"] = note
        emit(
            sid,
            EventType.ACTIVITY,
            payload,
            source_service="orchestrator",
            source_agent="error_repair",
        )

    def _ml() -> dict[str, Any]:
        nonlocal proposed
        # Fresh budget for each experiment; heal_used counts error_repair calls.
        heal_used = 0
        result: dict[str, Any] = {}

        while True:
            heal_meta = {
                "self_heal_attempt": heal_used,
                "self_heal_budget": SELF_HEAL_BUDGET,
                "retry_count": heal_used,
            }
            valid = _invoke(
                "ml_engineer",
                "config_validator",
                sid,
                {"experiment_spec": proposed, "session_id": sid},
                experiment_id=exp_id or None,
                extra_event=heal_meta,
            )
            if not valid.get("valid", True):
                err = "; ".join(valid.get("errors") or ["invalid config"])
                if heal_used >= SELF_HEAL_BUDGET:
                    _emit_heal(
                        attempt=heal_used,
                        trigger="invalid_config",
                        error=err,
                        exhausted=True,
                        note="self-heal budget exhausted",
                    )
                    return {
                        "latest_result": {
                            "experiment_id": proposed.get("experiment_id"),
                            "status": "failed",
                            "error": err,
                            "validation_metrics": {},
                            "train_metrics": {},
                            "self_heal_attempt": heal_used,
                            "self_heal_budget": SELF_HEAL_BUDGET,
                        },
                        "retry_count": heal_used,
                        "judge_verdict": {
                            "action": "reject",
                            "observation": "invalid config — self-heal exhausted",
                        },
                        "_skip_judge": True,
                    }
                attempt = heal_used + 1
                _emit_heal(attempt=attempt, trigger="invalid_config", error=err)
                repaired = _invoke(
                    "ml_engineer",
                    "error_repair",
                    sid,
                    {"error": err, "experiment_spec": proposed},
                    experiment_id=exp_id or None,
                    extra_event={
                        "self_heal_attempt": attempt,
                        "self_heal_budget": SELF_HEAL_BUDGET,
                        "retry_count": attempt,
                        "trigger": "invalid_config",
                    },
                )
                heal_used = attempt
                ok = bool(repaired.get("repaired"))
                _emit_heal(
                    attempt=attempt,
                    trigger="invalid_config",
                    error=err,
                    repaired=ok,
                    note=str(repaired.get("note") or ""),
                )
                if ok:
                    proposed = {**proposed, **(repaired.get("experiment_spec") or {})}
                    continue
                return {
                    "latest_result": {
                        "experiment_id": proposed.get("experiment_id"),
                        "status": "failed",
                        "error": err,
                        "validation_metrics": {},
                        "train_metrics": {},
                        "self_heal_attempt": heal_used,
                        "self_heal_budget": SELF_HEAL_BUDGET,
                    },
                    "retry_count": heal_used,
                    "judge_verdict": {"action": "reject", "observation": "invalid config"},
                    "_skip_judge": True,
                }

            result = _invoke(
                "ml_engineer",
                "experiment_runner",
                sid,
                {
                    "session_id": sid,
                    "dataset_id": state["dataset_id"],
                    "target_column": state["target_column"],
                    "experiment_spec": proposed,
                    "idempotency_key": f"{sid}:{proposed.get('experiment_id')}:h{heal_used}",
                },
                experiment_id=exp_id or None,
                extra_event=heal_meta,
            )
            if result.get("status") == "succeeded":
                break

            err = str(result.get("error") or "trial failed")
            if heal_used >= SELF_HEAL_BUDGET:
                _emit_heal(
                    attempt=heal_used,
                    trigger="trial_failed",
                    error=err,
                    exhausted=True,
                    note="self-heal budget exhausted",
                )
                break

            attempt = heal_used + 1
            _emit_heal(attempt=attempt, trigger="trial_failed", error=err)
            repaired = _invoke(
                "ml_engineer",
                "error_repair",
                sid,
                {"error": err, "experiment_spec": proposed},
                experiment_id=exp_id or None,
                extra_event={
                    "self_heal_attempt": attempt,
                    "self_heal_budget": SELF_HEAL_BUDGET,
                    "retry_count": attempt,
                    "trigger": "trial_failed",
                },
            )
            heal_used = attempt
            ok = bool(repaired.get("repaired"))
            _emit_heal(
                attempt=attempt,
                trigger="trial_failed",
                error=err,
                repaired=ok,
                note=str(repaired.get("note") or ""),
            )
            if ok:
                proposed = {**proposed, **(repaired.get("experiment_spec") or {})}
                continue
            break

        try:
            with httpx.Client(timeout=30.0) as client:
                client.post(
                    f"{TRACKING_URL}/runs",
                    headers=_headers(),
                    json={
                        "session_id": sid,
                        "experiment_id": result.get("experiment_id") or proposed.get("experiment_id"),
                        "config": proposed,
                        "metrics": result.get("validation_metrics") or {},
                        "tags": {
                            "phase": "validation",
                            "self_heal_attempt": heal_used,
                            "self_heal_budget": SELF_HEAL_BUDGET,
                        },
                        "idempotency_key": f"trk-{proposed.get('experiment_id')}-h{heal_used}",
                    },
                )
        except Exception:  # noqa: BLE001
            pass

        history = list(state.get("experiment_history") or [])
        history.append(
            {
                **result,
                "model_family": proposed.get("model_family"),
                "hyperparameters": proposed.get("hyperparameters"),
                "self_heal_attempt": heal_used,
                "self_heal_budget": SELF_HEAL_BUDGET,
            }
        )
        count = int(state.get("experiment_count") or 0) + 1
        best_id = state.get("best_experiment_id")
        best_score = float(state.get("best_val_score") or -1.0)
        val = float(((result.get("validation_metrics") or {}).get("f1") or -1.0))
        model_ref = result.get("model_ref") or state.get("model_ref")
        if val > best_score:
            best_score = val
            best_id = result.get("experiment_id")
            model_ref = result.get("model_ref") or model_ref

        emit(
            sid,
            EventType.BUDGET_UPDATE,
            {
                "experiment_count": count,
                "experiment_budget": state.get("experiment_budget"),
                "best_val_score": best_score,
                "experiment_id": exp_id,
                "self_heal_attempt": heal_used,
                "self_heal_budget": SELF_HEAL_BUDGET,
            },
        )
        return {
            "result": result,
            "history": history,
            "count": count,
            "best_id": best_id,
            "best_score": best_score,
            "model_ref": model_ref,
            "retry_count": heal_used,
        }

    ml_out = _with_lead(sid, "ml_engineer", _ml)
    if ml_out.get("_skip_judge"):
        return {k: v for k, v in ml_out.items() if not k.startswith("_")}

    result = ml_out["result"]
    history = ml_out["history"]
    count = ml_out["count"]
    best_id = ml_out["best_id"]
    best_score = ml_out["best_score"]
    model_ref = ml_out["model_ref"]
    heal_used = int(ml_out.get("retry_count") or 0)

    # Prior trials for the judge (exclude the just-finished row's incomplete verdict).
    prior_for_judge = _recent_experiments(history[:-1] if history else [])

    def _judge() -> dict[str, Any]:
        metrics = _invoke(
            "judge",
            "metric_analyst",
            sid,
            {"result": result, "recent_experiments": prior_for_judge},
            experiment_id=exp_id or None,
        )
        overfit = _invoke(
            "judge",
            "overfitting_checker",
            sid,
            {"result": result, "gap": metrics.get("gap"), "recent_experiments": prior_for_judge},
            experiment_id=exp_id or None,
        )
        budget_left = int(state.get("experiment_budget") or 10) - count
        verdict = _invoke(
            "judge",
            "independent_reviewer",
            sid,
            {
                "result": result,
                "target_score": state.get("target_score", 0.75),
                "budget_left": budget_left,
                "overfitting_risk": overfit.get("overfitting_risk"),
                "experiment_history": history,
                "recent_experiments": prior_for_judge,
            },
            experiment_id=exp_id or None,
        )
        verdict["overfitting_risk"] = overfit.get("overfitting_risk")
        return {"verdict": verdict}

    judge_out = _with_lead(sid, "judge", _judge)
    verdict = judge_out["verdict"]

    # Stamp judge outcome onto the latest history row so the next proposal sees it.
    if history:
        history = list(history)
        history[-1] = {
            **history[-1],
            "judge_action": verdict.get("action"),
            "judge_observation": verdict.get("observation"),
            "next_action": verdict.get("next_action"),
        }

    # Persist a compact finding so memory_retriever can reload session context.
    try:
        with httpx.Client(timeout=15.0) as client:
            client.post(
                f"{MEMORY_URL}/findings",
                headers=_headers(),
                json={
                    "session_id": sid,
                    "writer": "orchestrator",
                    "content": {
                        "kind": "experiment_result",
                        "experiment": _recent_experiments(history)[-1] if history else {},
                        "best_val_score": best_score,
                        "best_experiment_id": best_id,
                    },
                    "idempotency_key": f"finding-{exp_id or count}",
                },
            )
            client.post(
                f"{MEMORY_URL}/history",
                headers=_headers(),
                json={
                    "session_id": sid,
                    "writer": "orchestrator",
                    "content": {
                        "kind": "experiment_result",
                        "experiment": _recent_experiments(history)[-1] if history else {},
                    },
                    "idempotency_key": f"hist-{exp_id or count}",
                },
            )
    except Exception:  # noqa: BLE001
        pass

    return {
        "latest_result": result,
        "experiment_history": history,
        "experiment_count": count,
        "judge_verdict": verdict,
        "best_experiment_id": best_id,
        "best_val_score": best_score,
        "model_ref": model_ref,
        # Reset for the next experiment; heal budget is per-experiment.
        "retry_count": 0,
        "self_heal_last": heal_used,
    }


def node_finalize(state: ResearchStateDict) -> ResearchStateDict:
    sid = state["session_id"]
    model_ref = state.get("model_ref")
    holdout = None
    if model_ref:
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(
                    f"{DATASET_URL}/internal/holdout/evaluate",
                    headers={**_headers(), "X-Harness-Token": HARNESS_TOKEN},
                    json={
                        "session_id": sid,
                        "dataset_id": state["dataset_id"],
                        "model_ref": model_ref,
                        "metric": state.get("metric") or "f1",
                        "idempotency_key": f"holdout-{sid}",
                    },
                )
                if r.status_code < 400:
                    holdout = r.json()
                    client.post(
                        f"{TRACKING_URL}/runs",
                        headers=_headers(),
                        json={
                            "session_id": sid,
                            "experiment_id": f"final-{state.get('best_experiment_id')}",
                            "config": {"phase": "holdout"},
                            "metrics": {"holdout_f1": holdout.get("score")},
                            "tags": {"final": "true", "phase": "holdout"},
                            "idempotency_key": f"final-{sid}",
                        },
                    )
        except Exception:  # noqa: BLE001
            holdout = None

    if holdout is not None:
        emit(
            sid,
            EventType.HOLDOUT_EVALUATED,
            {"score": holdout.get("score"), "metric": state.get("metric") or "f1"},
            source_service="dataset_service",
        )

    try:
        with httpx.Client(timeout=15.0) as client:
            client.post(
                f"{MEMORY_URL}/history",
                headers=_headers(),
                json={
                    "session_id": sid,
                    "writer": "orchestrator",
                    "content": {
                        "best_experiment_id": state.get("best_experiment_id"),
                        "best_val_score": state.get("best_val_score"),
                        "holdout": holdout,
                    },
                    "idempotency_key": f"mem-hist-{sid}",
                },
            )
    except Exception:  # noqa: BLE001
        pass

    stop_reason = state.get("stop_reason") or "finalize"
    emit(
        sid,
        EventType.AGENT_COMPLETED,
        {"lead": "meta_supervisor", "stop_reason": stop_reason},
        source_service="orchestrator",
        source_agent="meta_supervisor",
    )
    emit(
        sid,
        EventType.STOP_REASON,
        {
            "stop_reason": stop_reason,
            "best_experiment_id": state.get("best_experiment_id"),
            "best_val_score": state.get("best_val_score"),
            "holdout_score": None if holdout is None else holdout.get("score"),
        },
    )
    return {
        "status": "completed",
        "stop_reason": stop_reason,
        "holdout_score": None if holdout is None else holdout.get("score"),
    }


def _route_after_judge(state: ResearchStateDict) -> str:
    budget = int(state.get("experiment_budget") or 10)
    count = int(state.get("experiment_count") or 0)
    verdict = (state.get("judge_verdict") or {}).get("action")
    if count >= budget:
        return "finalize"
    if verdict in {"accept", "stop"}:
        return "finalize"
    # reject = drop this experiment; revise = tweak next — both keep spending budget.
    if verdict in {"revise", "reject"}:
        return "hypothesize"
    return "finalize"


def build_graph():
    g = StateGraph(ResearchStateDict)
    g.add_node("profile", node_profile)
    g.add_node("hypothesize", node_hypothesize)
    g.add_node("run", node_run)
    g.add_node("finalize", node_finalize)
    g.set_entry_point("profile")
    g.add_edge("profile", "hypothesize")
    g.add_edge("hypothesize", "run")
    g.add_conditional_edges(
        "run", _route_after_judge, {"hypothesize": "hypothesize", "finalize": "finalize"}
    )
    g.add_edge("finalize", END)
    return g.compile(checkpointer=MemorySaver())


GRAPH = build_graph()
