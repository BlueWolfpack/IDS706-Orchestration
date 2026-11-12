"""Fraud research loop — the in-class LangGraph loop adapted to the Airflow output.

Flow (changes vs the class template marked):
  START → warehouse_loader [NEW] → data_scientist [MODIFIED] → baseline_agent [NEW]
        → hypothesis_generator → ml_engineer [MODIFIED] → judge [MODIFIED] → router
              ↑                                                             │
              └──── memory_writer [MODIFIED: absorbs context_builder] ◄─────┤ revise
                                                                            │ accept / stop
                                     holdout_eval → evaluation_reporter [NEW] → END

  * warehouse_loader     reads analytics.fraud_transactions (written by the Airflow DAG) from
                         Postgres; falls back to the CSV picked in the UI.
  * data_scientist       adds a data-driven leakage scan (single-feature ROC-AUC ≥ 0.95,
                         ids, raw datetimes). The LLM can add drops but can never un-drop a leak.
  * baseline_agent       majority / stratified dummy scores on the same split — with 3 % fraud a
                         majority classifier already scores ~97 % accuracy, so accuracy alone lies.
  * ml_engineer          probability models with class weights + F1-optimal threshold on val.
  * judge                F1 vs target, PR-AUC lift vs prevalence; new `stop` action ends the loop
                         early when two cycles show no learnable signal.
  * context_builder      REMOVED — memory_writer now files the lesson and builds the brief.
  * evaluation_reporter  writes lab/langgraph/reports/latest_eval.{json,md} with holdout vs baseline.

LLM / train helpers: loop_runtime.py (class) + fraud_tools.py (this assignment).
"""

from __future__ import annotations

import json
import operator
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
for _p in (REPO, Path("/app"), ROOT):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from loop_runtime import (  # noqa: E402
    DEFAULT_MODEL,
    FAMILIES,
    _SPEC_SCHEMA_HINT,
    _coerce_experiment_spec,
    _heuristic_plan,
    _heuristic_profile,
    _heuristic_spec,
    _repair_heuristic,
    _resolve_model,
    _validate_spec,
    extract_json_object,
    llm_configured,
    openrouter_chat,
)

try:  # package import inside the gateway, plain import from the CLI
    from lab.langgraph import fraud_tools as ft  # noqa: E402
except ImportError:  # pragma: no cover
    import fraud_tools as ft  # type: ignore  # noqa: E402

REPORTS = ROOT / "reports"
SNAPSHOT = ROOT / "runs" / "warehouse_snapshot.csv"
NO_SIGNAL_LIFT = 1.25  # PR-AUC must beat prevalence by 25 % to count as "signal"
NO_SIGNAL_MIN_CYCLES = 3  # try every model family before giving up


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------
class SimpleLoopState(TypedDict, total=False):
    dataset_path: str
    source_dataset: str
    target_column: str
    target_score: float
    max_cycles: int
    cycle: int
    seed: int
    holdout_frac: float
    model: str
    warehouse: dict  # NEW: where the data came from
    profile: dict
    leakage: dict  # NEW: data-driven leakage scan
    baseline: dict  # NEW: dummy baselines
    brief: dict
    hypothesis: dict
    experiment_spec: dict
    execution_result: dict
    verdict: dict
    memory: dict
    best_spec: dict
    best_val_f1: float
    best_val_pr_auc: float
    best_threshold: float
    holdout_metrics: dict
    report: dict  # NEW: evaluation report
    stop_reason: str
    steps: Annotated[list, operator.add]


def _read(state: SimpleLoopState) -> pd.DataFrame:
    return pd.read_csv(state["dataset_path"])


def _history(state: SimpleLoopState) -> list:
    brief = state.get("brief") or {}
    return list(brief.get("history") or (state.get("memory") or {}).get("history") or [])


def _required_drops(state: SimpleLoopState) -> list[str]:
    """Leakage guardrail — these columns are dropped no matter what any agent proposes."""
    return list((state.get("leakage") or {}).get("drops") or [])


# ---------------------------------------------------------------------------
# NODES
# ---------------------------------------------------------------------------
def node_warehouse_loader(state: SimpleLoopState) -> dict:
    """NEW — pull the Airflow-cleaned table from Postgres; fall back to the selected CSV."""
    picked = state["dataset_path"]
    res = ft.load_from_warehouse(SNAPSHOT)
    if res.get("ok"):
        df = pd.read_csv(res["path"])
        if state["target_column"] in df.columns:
            info = {"source": "postgres", **res, "fallback_csv": picked}
            return {
                "dataset_path": res["path"],
                "warehouse": info,
                "steps": [
                    {
                        "node": "warehouse_loader",
                        "note": f"postgres {res['table']} · {res['rows']} rows",
                        "output": info,
                    }
                ],
            }
        res = {"ok": False, "reason": f"target {state['target_column']!r} not in warehouse table"}
    info = {"source": "csv", "path": picked, "reason": res.get("reason")}
    return {
        "warehouse": info,
        "steps": [
            {
                "node": "warehouse_loader",
                "note": f"csv fallback ({res.get('reason')})",
                "output": info,
            }
        ],
    }


def node_data_scientist(state: SimpleLoopState) -> dict:
    """MODIFIED — profile + data-driven leakage scan (guardrail the LLM cannot override)."""
    df = _read(state)
    target = state["target_column"]
    if target not in df.columns:
        return {
            "profile": {},
            "steps": [{"node": "data_scientist", "note": f"target {target!r} missing", "status": "error"}],
        }

    leak = ft.leakage_scan(df, target)
    profile = _heuristic_profile(df, target)
    used_llm, note = False, "heuristic profile"
    model = _resolve_model(state)

    if llm_configured(model):
        system = (
            "You are the Data Scientist for a FRAUD DETECTION dataset (binary target, rare positives). "
            "Profile the data and flag risk only — do NOT propose models or hyperparameters. "
            "Return ONLY one JSON object with keys: n_rows, n_columns, target, target_rate, "
            "numeric_features (string[]), categorical_features (string[]), leakage_suspects (string[]), "
            "recommended_drops (string[]), notes (string[] — imbalance, leakage, weak signal). "
            "A precomputed score that separates the label almost perfectly is leakage, not a feature."
        )
        user = (
            f"target={target}\nn_rows={len(df)}\ntarget_rate={float(df[target].mean()):.4f}\n"
            f"columns={list(df.columns)}\n"
            f"single_feature_roc_auc={json.dumps(leak['top_single_feature_auc'])}\n"
            f"automatic_leakage_flags={json.dumps(leak)}\n"
            f"sample_rows={df.head(4).astype(str).to_dict(orient='records')}\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=900, temperature=0.15)
        parsed = extract_json_object(content or "")
        if parsed and ("recommended_drops" in parsed or "leakage_suspects" in parsed):
            profile = {**profile, **parsed}
            used_llm, note = True, f"llm profile · {model}"
        else:
            note = f"{err or 'llm unparsable'}; heuristic profile"

    drops = sorted(set(list(profile.get("recommended_drops") or []) + leak["drops"]))
    profile["recommended_drops"] = drops
    profile["leakage_suspects"] = sorted(set(list(profile.get("leakage_suspects") or []) + leak["leaky_columns"]))
    profile.setdefault("notes", [])
    if leak["leaky_columns"]:
        profile["notes"] = list(profile["notes"]) + [
            f"Leakage: {', '.join(leak['leaky_columns'])} alone predicts {target} "
            f"(single-feature AUC ≥ {ft.LEAK_AUC}) — dropped."
        ]
    note += f" · leakage scan dropped {len(drops)} cols ({', '.join(leak['leaky_columns']) or 'no leaks'})"
    return {
        "profile": profile,
        "leakage": leak,
        "steps": [
            {
                "node": "data_scientist",
                "note": note,
                "used_llm": used_llm,
                "model": model if used_llm else None,
                "output": {**profile, "leakage_scan": leak},
            }
        ],
    }


def node_baseline_agent(state: SimpleLoopState) -> dict:
    """NEW — what does 'doing nothing' score on this exact split?"""
    df = _read(state)
    base = ft.baseline_scores(
        df, state["target_column"], _required_drops(state),
        int(state.get("seed") or 42), float(state.get("holdout_frac") or 0.2),
    )
    mf, ap = base["most_frequent"], base["always_positive"]
    note = (
        f"prevalence {base['prevalence']:.3f} · majority-class acc {mf['accuracy']:.3f} (F1 0) · "
        f"flag-everything F1 {ap['f1']:.3f} → a model must beat both"
    )
    return {"baseline": base, "steps": [{"node": "baseline_agent", "note": note, "output": base}]}


def node_hypothesis(state: SimpleLoopState) -> dict:
    """Conceptual next experiment from profile + baseline + judge feedback (no HPT numbers)."""
    profile = state.get("profile") or {}
    verdict = state.get("verdict") or {}
    history = _history(state)
    model = _resolve_model(state)
    plan = _heuristic_plan(profile, history, verdict)
    plan["respect_drops"] = sorted(set(list(plan.get("respect_drops") or []) + _required_drops(state)))
    tried = {h.get("model_family") for h in history}
    if history and any(f not in tried for f in FAMILIES):
        # Fraud-specific fallback: a weak signal is not fixed by tuning C — explore families first.
        plan["focus"] = "model_family_switch"
        plan["direction"] = f"Switch model family (tried: {', '.join(sorted(t for t in tried if t))})."
    used_llm, note = False, "heuristic plan"

    if llm_configured(model):
        system = (
            "You are the Hypothesis Generator for an imbalanced fraud classifier. "
            "Propose ONE conceptual next experiment — no hyperparameter numbers. "
            "Return ONLY JSON with keys: direction, why, "
            "focus (baseline_then_iterate|capacity_or_regularization|model_family_switch|feature_drops), "
            "respect_drops (string[]), avoid_repeats (string[])."
        )
        user = (
            f"profile_notes={json.dumps(profile.get('notes'), default=str)}\n"
            f"baseline={json.dumps(state.get('baseline'), default=str)}\n"
            f"latest_verdict={json.dumps(verdict, default=str)}\n"
            f"lessons={json.dumps((state.get('brief') or {}).get('lessons'), default=str)}\n"
            f"recent_history={json.dumps(history[-4:], default=str)}\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=500, temperature=0.4)
        parsed = extract_json_object(content or "")
        if parsed and parsed.get("direction"):
            plan.update({k: parsed[k] for k in ("direction", "why", "focus", "avoid_repeats") if parsed.get(k)})
            used_llm, note = True, f"live conceptual hypothesis · {model}"
        else:
            note = f"{err or 'llm unparsable'}; heuristic plan"

    return {
        "hypothesis": plan,
        "steps": [
            {
                "node": "hypothesis_generator",
                "note": note,
                "hypothesis": plan,
                "output": plan,
                "used_llm": used_llm,
                "model": model if used_llm else None,
            }
        ],
    }


def node_ml_engineer(state: SimpleLoopState) -> dict:
    """MODIFIED — concrete spec → class-weighted model → F1-optimal threshold on validation."""
    df = _read(state)
    target = state["target_column"]
    profile = state.get("profile") or {}
    plan = dict(state.get("hypothesis") or {})
    history = _history(state)
    seed = int(state.get("seed") or 42)
    holdout_frac = float(state.get("holdout_frac") or 0.2)
    model_id = _resolve_model(state)
    next_eid = f"exp-{len(history) + 1}"

    spec = _heuristic_spec(profile, history, plan)
    used_llm, repaired, note = False, False, "heuristic HPT"
    if llm_configured(model_id):
        system = (
            "You are the ML Engineer. Translate the plan into ONE concrete training config. "
            f"Return ONLY JSON matching: {_SPEC_SCHEMA_HINT} "
            f"model_family must be one of {list(FAMILIES)}. Class weights and threshold tuning are "
            "applied automatically — choose capacity / regularisation only."
        )
        user = (
            f"plan={json.dumps(plan, default=str)}\n"
            f"prior_spec={json.dumps(state.get('experiment_spec') or {}, default=str)}\n"
            f"recent_history={json.dumps(history[-3:], default=str)}\nnext_experiment_id={next_eid}\n"
        )
        content, err = openrouter_chat(system, user, model=model_id, max_tokens=600, temperature=0.2, json_object=True)
        coerced = _coerce_experiment_spec(
            extract_json_object(content or ""), experiment_id=next_eid, default_drops=plan.get("respect_drops")
        )
        if coerced:
            spec, used_llm, note = coerced, True, f"live HPT config · {model_id}"
        else:
            note = f"{err or 'llm unparsable'}; heuristic HPT"

    spec["experiment_id"] = next_eid
    # Guardrail: leakage columns are always dropped, whatever the LLM wrote.
    spec["drop_columns"] = sorted(set(list(spec.get("drop_columns") or []) + _required_drops(state)))
    err = _validate_spec(spec)
    if err:
        spec, repaired, note = _repair_heuristic(spec, err), True, f"heuristic repair after: {err}"
        spec["drop_columns"] = sorted(set(list(spec.get("drop_columns") or []) + _required_drops(state)))

    cycle = int(state.get("cycle") or 0) + 1
    try:
        result = ft.fit_eval(df, target, spec, seed, holdout_frac, on_holdout=False)
    except Exception as exc:  # noqa: BLE001 — self-heal once with a safe config
        spec = _repair_heuristic(spec, str(exc))
        spec["drop_columns"] = sorted(set(list(spec.get("drop_columns") or []) + _required_drops(state)))
        repaired, note = True, f"heuristic repair after run error: {str(exc)[:120]}"
        try:
            result = ft.fit_eval(df, target, spec, seed, holdout_frac, on_holdout=False)
        except Exception as exc2:  # noqa: BLE001
            result = {"status": "failed", "error": str(exc2), "validation_metrics": {}}

    vm = result.get("validation_metrics") or {}
    f1 = float(vm.get("f1") or 0)
    ok = result.get("status") == "succeeded"
    if ok:
        note = (
            f"{note} · {spec['model_family']} f1={f1:.3f} @thr {vm.get('threshold', 0):.2f} "
            f"pr_auc={vm.get('pr_auc') or 0:.3f} acc={vm.get('accuracy', 0):.3f}"
        )
    patch: dict = {
        "execution_result": result,
        "experiment_spec": spec,
        "cycle": cycle,
        "steps": [
            {
                "node": "ml_engineer",
                "note": note,
                "f1": f1 if ok else None,
                "status": result.get("status"),
                "repaired": repaired,
                "used_llm": used_llm,
                "experiment_id": spec.get("experiment_id"),
                "model_family": spec.get("model_family"),
                "validation_metrics": {k: v for k, v in vm.items() if isinstance(v, (int, float))},
                "duration_seconds": result.get("duration_seconds"),
                "spec": spec,
                "output": {"experiment_spec": spec, "execution_result": result},
            }
        ],
    }
    if ok and (f1, vm.get("pr_auc") or 0) > (
        float(state.get("best_val_f1") or -1), float(state.get("best_val_pr_auc") or -1)
    ):
        patch.update(
            best_val_f1=f1,
            best_val_pr_auc=float(vm.get("pr_auc") or 0),
            best_spec=spec,
            best_threshold=float(vm.get("threshold") or 0.5),
        )
    return patch


def _heuristic_fraud_verdict(state: SimpleLoopState) -> dict:
    result = state.get("execution_result") or {}
    target_score = float(state.get("target_score") or 0.8)
    cycle = int(state.get("cycle") or 0)
    prevalence = float((state.get("baseline") or {}).get("prevalence") or 0.0)
    vm = result.get("validation_metrics") or {}
    f1, pr = float(vm.get("f1") or 0), float(vm.get("pr_auc") or 0)
    floor = float(((state.get("baseline") or {}).get("always_positive") or {}).get("f1") or 0)
    best_pr = max(float(state.get("best_val_pr_auc") or 0), pr)
    lift = best_pr / prevalence if prevalence else 0.0
    if result.get("status") != "succeeded":
        return {"action": "revise", "observation": f"run failed: {result.get('error')}", "next_action": "safer config"}
    if f1 >= 0.99:
        return {
            "action": "revise",
            "observation": f"val F1 {f1:.3f} is suspiciously perfect — likely leakage",
            "next_action": "drop the leaking column and retry",
        }
    if f1 >= target_score:
        return {"action": "accept", "observation": f"val F1 {f1:.3f} meets target {target_score:.2f}", "next_action": "finalize"}
    if cycle >= NO_SIGNAL_MIN_CYCLES and lift < NO_SIGNAL_LIFT:
        return {
            "action": "stop",
            "observation": (
                f"after {cycle} cycles best PR-AUC {best_pr:.3f} is only {lift:.2f}× the {prevalence:.3f} "
                f"fraud rate and F1 {f1:.3f} ≈ flag-everything {floor:.3f} — no learnable signal"
            ),
            "next_action": "stop searching; report holdout vs baseline",
        }
    return {
        "action": "revise",
        "observation": (
            f"val F1 {f1:.3f} below target {target_score:.2f} (flag-everything floor {floor:.3f}); "
            f"PR-AUC lift {lift:.2f}×"
        ),
        "next_action": "try a different model family or capacity",
    }


def node_judge(state: SimpleLoopState) -> dict:
    """MODIFIED — judges F1 + PR-AUC lift over baseline; can now `stop` early."""
    verdict = _heuristic_fraud_verdict(state)
    model = _resolve_model(state)
    used_llm, note = False, "heuristic verdict"
    if llm_configured(model):
        system = (
            "You are the Judge for an imbalanced fraud model. Decide from VALIDATION evidence only. "
            "Return ONLY JSON: action (accept|revise|stop), observation (1-2 sentences citing F1 and "
            "PR-AUC vs fraud rate), next_action (conceptual, no numbers). accept only if F1 ≥ target; "
            "stop if repeated cycles show PR-AUC barely above the fraud rate; otherwise revise."
        )
        user = (
            f"target_f1={state.get('target_score')}\ncycle={state.get('cycle')}\n"
            f"baseline={json.dumps(state.get('baseline'), default=str)}\n"
            f"result={json.dumps(state.get('execution_result'), default=str)}\n"
            f"heuristic_suggestion={json.dumps(verdict)}\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=400, temperature=0.1)
        parsed = extract_json_object(content or "")
        if parsed and parsed.get("action") in {"accept", "revise", "stop"}:
            llm_v = {k: parsed.get(k) or verdict.get(k) for k in ("action", "observation", "next_action")}
            # Guardrail: never accept below target.
            f1 = float(((state.get("execution_result") or {}).get("validation_metrics") or {}).get("f1") or 0)
            if llm_v["action"] == "accept" and f1 < float(state.get("target_score") or 0.8):
                llm_v["action"] = verdict["action"]
            verdict, used_llm, note = llm_v, True, f"llm verdict · {model}"
        else:
            note = f"{err or 'llm unparsable'}; heuristic verdict"
    return {
        "verdict": verdict,
        "steps": [
            {"node": "judge", "note": f"{verdict['action']}: {verdict['observation']}", "verdict": verdict,
             "used_llm": used_llm, "model": model if used_llm else None, "detail": note}
        ],
    }


def node_memory_writer(state: SimpleLoopState) -> dict:
    """MODIFIED — files the lesson AND builds the next brief (context_builder removed)."""
    mem = dict(state.get("memory") or {"history": [], "findings": [], "lessons": []})
    vm = (state.get("execution_result") or {}).get("validation_metrics") or {}
    hist = list(mem.get("history") or []) + [
        {
            "cycle": state.get("cycle"),
            "hypothesis": state.get("hypothesis"),
            "spec": state.get("experiment_spec"),
            "model_family": (state.get("experiment_spec") or {}).get("model_family"),
            "f1": vm.get("f1"),
            "pr_auc": vm.get("pr_auc"),
            "verdict": state.get("verdict"),
        }
    ]
    lessons = list(mem.get("lessons") or []) + [str((state.get("verdict") or {}).get("observation") or "")]
    mem.update(history=hist, lessons=lessons)
    brief = {"history": hist, "lessons": lessons[-3:], "baseline": state.get("baseline")}
    return {
        "memory": mem,
        "brief": brief,
        "steps": [{"node": "memory_writer", "note": f"filed lesson #{len(lessons)} + built brief"}],
    }


def node_holdout(state: SimpleLoopState) -> dict:
    """Score the best spec ONCE on the sealed holdout with its val-tuned threshold."""
    df = _read(state)
    spec = dict(state.get("best_spec") or state.get("experiment_spec") or {})
    if _validate_spec(spec):
        spec = _repair_heuristic(spec, "invalid best_spec")
    spec["drop_columns"] = sorted(set(list(spec.get("drop_columns") or []) + _required_drops(state)))
    metrics = ft.fit_eval(
        df, state["target_column"], spec, int(state.get("seed") or 42), float(state.get("holdout_frac") or 0.2),
        on_holdout=True, threshold=float(state.get("best_threshold") or 0.5),
    )
    action = (state.get("verdict") or {}).get("action")
    return {
        "holdout_metrics": metrics,
        "stop_reason": {"accept": "target_met", "stop": "no_signal"}.get(action, "budget_exhausted"),
        "steps": [
            {
                "node": "holdout_eval",
                "note": f"holdout f1 {metrics['f1']:.3f} · acc {metrics['accuracy']:.3f} · pr_auc {metrics.get('pr_auc') or 0:.3f}",
                "metrics": metrics,
            }
        ],
    }


def node_evaluation_reporter(state: SimpleLoopState) -> dict:
    """NEW — compare holdout vs baseline and write a report the README can link to."""
    hold = state.get("holdout_metrics") or {}
    base = state.get("baseline") or {}
    mf = base.get("most_frequent") or {}
    ap = base.get("always_positive") or {}
    prevalence = float(base.get("prevalence") or 0)
    history = list((state.get("memory") or {}).get("history") or [])
    if int(state.get("cycle") or 0) > len(history):  # last cycle never reached memory_writer
        vm = (state.get("execution_result") or {}).get("validation_metrics") or {}
        history.append(
            {"cycle": state.get("cycle"), "model_family": (state.get("experiment_spec") or {}).get("model_family"),
             "f1": vm.get("f1"), "pr_auc": vm.get("pr_auc"), "verdict": state.get("verdict")}
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": (state.get("warehouse") or {}).get("source"),
        "target": state.get("target_column"),
        "cycles": state.get("cycle"),
        "stop_reason": state.get("stop_reason"),
        "dropped_for_leakage": (state.get("leakage") or {}).get("leaky_columns"),
        "best_spec": state.get("best_spec"),
        "best_val_f1": state.get("best_val_f1"),
        "holdout": hold,
        "baseline_majority": mf,
        "baseline_always_positive": ap,
        "f1_gain_vs_majority": round(float(hold.get("f1") or 0) - float(mf.get("f1") or 0), 4),
        "pr_auc_lift_vs_prevalence": round(float(hold.get("pr_auc") or 0) / prevalence, 3) if prevalence else None,
        "experiments": [
            {"cycle": h.get("cycle"), "family": h.get("model_family"), "val_f1": h.get("f1"), "val_pr_auc": h.get("pr_auc"),
             "verdict": (h.get("verdict") or {}).get("action")}
            for h in history
        ],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "latest_eval.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    rows = "\n".join(
        f"| {m} | {mf.get(m) or 0:.3f} | {ap.get(m) or 0:.3f} | {hold.get(m) or 0:.3f} |"
        for m in ("accuracy", "balanced_accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc")
    )
    md = (
        f"# Agent loop evaluation ({report['generated_at']})\n\n"
        f"Data source: **{report['data_source']}** · target `{report['target']}` · cycles {report['cycles']} · "
        f"stop reason `{report['stop_reason']}`\n\n"
        f"Dropped for leakage: {', '.join(report['dropped_for_leakage'] or []) or 'none'}\n\n"
        f"Best spec: `{json.dumps(report['best_spec'], default=str)}`\n\n"
        "Baselines are scored on the validation split; the agent model on the sealed holdout.\n\n"
        "| metric | majority-class baseline | flag-everything baseline | best agent model (holdout) |\n"
        "| --- | --- | --- | --- |\n"
        f"{rows}\n\n"
        "| cycle | model family | val F1 | val PR-AUC | judge |\n| --- | --- | --- | --- | --- |\n"
        + "\n".join(
            f"| {e['cycle']} | {e['family']} | {e['val_f1']} | {e['val_pr_auc']} | {e['verdict']} |"
            for e in report["experiments"]
        )
        + "\n"
    )
    (REPORTS / "latest_eval.md").write_text(md, encoding="utf-8")
    note = (
        f"holdout F1 {hold.get('f1', 0):.3f} vs baseline {mf.get('f1', 0):.3f} · "
        f"PR-AUC lift {report['pr_auc_lift_vs_prevalence']}× · report → lab/langgraph/reports/latest_eval.md"
    )
    return {"report": report, "steps": [{"node": "evaluation_reporter", "note": note, "output": report}]}


def route_after_judge(state: SimpleLoopState) -> str:
    """Router = plain code. accept/stop → holdout; revise with budget left → memory."""
    action = str((state.get("verdict") or {}).get("action") or "stop")
    if action == "revise" and int(state.get("cycle") or 0) < int(state.get("max_cycles") or 3):
        return "memory"
    return "holdout"


# ---------------------------------------------------------------------------
# GRAPH WIRING
# ---------------------------------------------------------------------------
def build_graph():
    g = StateGraph(SimpleLoopState)

    g.add_node("warehouse_loader", node_warehouse_loader)
    g.add_node("data_scientist", node_data_scientist)
    g.add_node("baseline_agent", node_baseline_agent)
    g.add_node("hypothesis_generator", node_hypothesis)
    g.add_node("ml_engineer", node_ml_engineer)
    g.add_node("judge", node_judge)
    g.add_node("memory_writer", node_memory_writer)
    g.add_node("holdout_eval", node_holdout)
    g.add_node("evaluation_reporter", node_evaluation_reporter)

    g.add_edge(START, "warehouse_loader")
    g.add_edge("warehouse_loader", "data_scientist")
    g.add_edge("data_scientist", "baseline_agent")
    g.add_edge("baseline_agent", "hypothesis_generator")
    g.add_edge("hypothesis_generator", "ml_engineer")
    g.add_edge("ml_engineer", "judge")
    g.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "memory": "memory_writer",
            "holdout": "holdout_eval",
        },
    )
    g.add_edge("memory_writer", "hypothesis_generator")  # loop back (context_builder removed)
    g.add_edge("holdout_eval", "evaluation_reporter")
    g.add_edge("evaluation_reporter", END)
    return g.compile()


REQUIRED_NODES = frozenset(
    {
        "warehouse_loader",
        "data_scientist",
        "baseline_agent",
        "hypothesis_generator",
        "ml_engineer",
        "judge",
        "memory_writer",
        "holdout_eval",
        "evaluation_reporter",
    }
)


def scan_declared_nodes(source: str) -> list[str]:
    """Names passed to g.add_node(...) in source (order preserved, unique).

    Used so the UI can show boxes one-by-one before the graph compiles.
    """
    import re

    found: list[str] = []
    seen: set[str] = set()
    for name in re.findall(r"""\.add_node\(\s*['\"]([^'\"]+)['\"]""", source):
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def _edge_endpoint(token: str) -> str:
    t = token.strip()
    if t in {"START", "END"}:
        return "__start__" if t == "START" else "__end__"
    if (t.startswith("'") and t.endswith("'")) or (t.startswith('"') and t.endswith('"')):
        return t[1:-1]
    return t


def scan_declared_edges(source: str) -> list[dict[str, str]]:
    """Pairs from g.add_edge(...) and judge conditional map in source."""
    import re

    edges: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(src: str, dst: str) -> None:
        key = (src, dst)
        if key in seen or not src or not dst:
            return
        seen.add(key)
        edges.append({"source": src, "target": dst})

    for m in re.finditer(r"\.add_edge\(\s*([^,]+)\s*,\s*([^)]+)\)", source):
        add(_edge_endpoint(m.group(1)), _edge_endpoint(m.group(2)))

    # add_conditional_edges("judge", ..., {"memory": "memory_writer", "holdout": "holdout_eval"})
    if re.search(r"\.add_conditional_edges\(", source):
        if re.search(r"""['\"]memory['\"]\s*:\s*['\"]memory_writer['\"]""", source):
            add("judge", "memory_writer")
        if re.search(r"""['\"]holdout['\"]\s*:\s*['\"]holdout_eval['\"]""", source):
            add("judge", "holdout_eval")

    return edges


def partition_drawable_edges(
    nodes: list[str], edges: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[str]]:
    """Keep edges reachable from START; report the rest (not drawn on the UI)."""
    declared = set(nodes)
    adj: dict[str, list[str]] = {}
    for e in edges:
        adj.setdefault(e["source"], []).append(e["target"])

    reachable: set[str] = {"__start__"}
    stack = ["__start__"]
    while stack:
        cur = stack.pop()
        for nxt in adj.get(cur, []):
            if nxt not in reachable:
                reachable.add(nxt)
                stack.append(nxt)

    ok: list[dict[str, str]] = []
    problems: list[str] = []
    for e in edges:
        s, t = e["source"], e["target"]
        if s != "__start__" and s not in reachable:
            problems.append(f"{s} → {t} (unreachable from START — not drawn)")
            continue
        if t not in declared and t != "__end__":
            problems.append(f"{s} → {t} ({t} is not a declared node — not drawn)")
            continue
        ok.append(e)
    return ok, problems


def assess_graph_ready(app) -> dict:
    """Return readiness dict from a compiled LangGraph app."""
    raw = app.get_graph().nodes
    present = {n for n in raw if n not in {START, END, "__start__", "__end__"}}
    missing = sorted(REQUIRED_NODES - present)
    return {
        "ready": not missing,
        "nodes": sorted(present),
        "missing_nodes": missing,
        "error": None if not missing else f"missing nodes: {', '.join(missing)}",
    }


def get_status() -> dict:
    """Status for /lab-loop: partial nodes/edges for the canvas; ready when fully wired."""
    import inspect

    try:
        src = inspect.getsource(build_graph)
    except (OSError, TypeError):
        src = ""
    declared = scan_declared_nodes(src)
    declared_edges = scan_declared_edges(src)
    drawable, edge_problems = partition_drawable_edges(declared, declared_edges)
    missing = sorted(REQUIRED_NODES - set(declared))

    def _error(*parts: str | None) -> str | None:
        msgs = [p for p in parts if p]
        if edge_problems:
            msgs.append("dead edges: " + "; ".join(edge_problems))
        return " · ".join(msgs) if msgs else None

    try:
        app = build_graph()
    except NotImplementedError as exc:
        return {
            "ready": False,
            "nodes": declared,
            "edges": drawable,
            "missing_nodes": missing if missing else sorted(REQUIRED_NODES),
            "error": _error(str(exc) or "build_graph not implemented"),
        }
    except Exception as exc:  # noqa: BLE001
        # Partial wiring often fails compile — still show declared nodes/edges.
        return {
            "ready": False,
            "nodes": declared,
            "edges": drawable,
            "missing_nodes": missing,
            "error": _error(str(exc)),
        }

    assessed = assess_graph_ready(app)
    nodes = assessed["nodes"] or declared
    return {
        "ready": assessed["ready"],
        "nodes": nodes,
        "edges": drawable,
        "missing_nodes": assessed["missing_nodes"],
        "error": _error(assessed["error"]),
    }
def _initial_state(
    *,
    dataset_path: str,
    target_column: str,
    target_score: float,
    max_cycles: int,
    seed: int,
    holdout_frac: float,
    model: str | None = None,
) -> SimpleLoopState:
    state: SimpleLoopState = {
        "dataset_path": str(Path(dataset_path).resolve()),
        "target_column": target_column,
        "target_score": target_score,
        "max_cycles": max_cycles,
        "cycle": 0,
        "seed": seed,
        "holdout_frac": holdout_frac,
        "source_dataset": str(Path(dataset_path).resolve()),
        "best_val_f1": -1.0,
        "best_val_pr_auc": -1.0,
        "steps": [],
        "memory": {"history": [], "findings": [], "lessons": []},
        "brief": {},
    }
    chosen = (model or "").strip() or DEFAULT_MODEL
    state["model"] = chosen
    return state


def _finalize_payload(final: dict) -> dict:
    return {
        "dataset_path": final.get("dataset_path"),
        "target_column": final.get("target_column"),
        "cycles": final.get("cycle"),
        "best_val_f1": final.get("best_val_f1"),
        "best_spec": final.get("best_spec"),
        "holdout_metrics": final.get("holdout_metrics"),
        "verdict": final.get("verdict"),
        "stop_reason": final.get("stop_reason"),
        "profile": final.get("profile"),
        "memory": final.get("memory"),
        "model": final.get("model"),
        "warehouse": final.get("warehouse"),
        "leakage": final.get("leakage"),
        "baseline": final.get("baseline"),
        "best_val_pr_auc": final.get("best_val_pr_auc"),
        "best_threshold": final.get("best_threshold"),
        "report": final.get("report"),
        "steps": final.get("steps") or [],
    }


def run_lab_loop(
    *,
    dataset_path: str,
    target_column: str = "is_fraud",
    target_score: float = 0.8,
    max_cycles: int = 3,
    seed: int = 42,
    holdout_frac: float = 0.2,
    model: str | None = None,
) -> dict:
    """Run the whole graph to completion; return a summary dict."""
    app = build_graph()
    initial = _initial_state(
        dataset_path=dataset_path,
        target_column=target_column,
        target_score=target_score,
        max_cycles=max_cycles,
        seed=seed,
        holdout_frac=holdout_frac,
        model=model,
    )
    final = app.invoke(initial, config={"recursion_limit": 8 + max_cycles * 6})
    return _finalize_payload(final)


def stream_lab_loop(
    *,
    dataset_path: str,
    target_column: str = "is_fraud",
    target_score: float = 0.8,
    max_cycles: int = 3,
    seed: int = 42,
    holdout_frac: float = 0.2,
    model: str | None = None,
):
    """Yield UI events as each node starts/finishes (used by the gateway SSE)."""
    app = build_graph()
    initial = _initial_state(
        dataset_path=dataset_path,
        target_column=target_column,
        target_score=target_score,
        max_cycles=max_cycles,
        seed=seed,
        holdout_frac=holdout_frac,
        model=model,
    )
    yield {
        "type": "run_started",
        "dataset_path": str(Path(dataset_path).resolve()),
        "target_column": target_column,
        "model": initial.get("model"),
    }

    merged: dict = dict(initial)
    last_node: str | None = None
    try:
        for update in app.stream(
            initial, stream_mode="updates", config={"recursion_limit": 8 + max_cycles * 6}
        ):
            if not isinstance(update, dict):
                continue
            for node_name, patch in update.items():
                if last_node == "judge" and node_name in {"memory_writer", "holdout_eval"}:
                    action = str((merged.get("verdict") or {}).get("action") or "stop")
                    yield {
                        "type": "router",
                        "node": "router",
                        "status": "completed",
                        "action": action,
                        "route": "memory" if node_name == "memory_writer" else "holdout",
                    }
                    if node_name == "memory_writer":
                        yield {
                            "type": "node_completed",
                            "node": "research_memory",
                            "status": "completed",
                            "note": "history + lessons filed",
                        }

                yield {"type": "node_started", "node": node_name, "status": "running"}
                if isinstance(patch, dict):
                    steps = list(patch.get("steps") or [])
                    # Mirror Annotated[list, operator.add] — stream patches omit prior steps.
                    merged.update({k: v for k, v in patch.items() if k != "steps"})
                    if steps:
                        merged["steps"] = list(merged.get("steps") or []) + steps
                    note = steps[-1].get("note") if steps else None
                    yield {
                        "type": "node_completed",
                        "node": node_name,
                        "status": "completed",
                        "note": note,
                        "step": steps[-1] if steps else None,
                        "cycle": merged.get("cycle"),
                        "best_val_f1": merged.get("best_val_f1"),
                        "verdict": merged.get("verdict"),
                    }
                else:
                    yield {"type": "node_completed", "node": node_name, "status": "completed"}
                last_node = node_name
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "run_completed", "result": _finalize_payload(merged)}


if __name__ == "__main__":
    ds = REPO / "datasets" / "airflow" / "fraud_clean.csv"
    result = run_lab_loop(dataset_path=str(ds), target_column="is_fraud", max_cycles=4)
    print(json.dumps(result, indent=2, default=str))
