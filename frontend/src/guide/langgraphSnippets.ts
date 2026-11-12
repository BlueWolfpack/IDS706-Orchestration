// AUTO-GENERATED from solution/langgraph/graph.py — helpers live in loop_runtime.py (not shown to students).
// Keep in sync with solution/langgraph/graph.py (filled) and lab/langgraph/graph.py (skeleton).

export interface Snippet {
  id: string
  title: string
  hint: string
  code: string
}

export const STATUS_CMD = 'python -m lab.langgraph.run_cli --status'

export const NODE_SNIPPETS: Snippet[] = [
  {
    id: "data_scientist",
    title: "node_data_scientist",
    hint: "Profile CSV via LLM; heuristic fallback.",
    code: `    """Profile CSV via OpenRouter; heuristic fallback if key/parse fails."""
    path = Path(state["dataset_path"])
    target = state["target_column"]
    df = pd.read_csv(path)
    if target not in df.columns:
        return {
            "profile": {},
            "steps": [{"node": "data_scientist", "note": f"target {target!r} missing", "status": "error"}],
        }

    profile = _heuristic_profile(df, target)
    used_llm = False
    note = "heuristic"
    model = _resolve_model(state)

    if llm_configured(model):
        missing = {c: float(df[c].isna().mean()) for c in df.columns}
        nunique = {c: int(df[c].nunique(dropna=True)) for c in df.columns}
        sample = df.head(6).astype(str).replace("nan", "").to_dict(orient="records")
        system = (
            "You are the Data Scientist only — not the hypothesizer and not the ML engineer. "
            "Your job is dataset understanding: profile the CSV and flag risk. "
            "Do NOT propose model families, hyperparameters, or experiment configs. "
            "Return ONLY one JSON object with keys: "
            "n_rows (int), n_columns (int), target (string), target_rate (number|null), "
            "numeric_features (string[]), categorical_features (string[]), "
            "leakage_suspects (string[]), recommended_drops (string[]), "
            "notes (string[], short bullets about data risks — leakage, imbalance, sparsity). "
            "Flag PassengerId/Name/Ticket/Cabin-style identifiers and near-unique text as leakage. "
            "Do not invent columns that are not present."
        )
        user = (
            f"dataset={path.name}\\ntarget={target}\\nn_rows={len(df)}\\n"
            f"columns={list(df.columns)}\\n"
            f"dtypes={{{', '.join(f'{c}:{df[c].dtype}' for c in df.columns)}}}\\n"
            f"missing_rate={missing}\\nnunique={nunique}\\n"
            f"sample_rows={sample}\\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=900, temperature=0.15)
        if content:
            parsed = extract_json_object(content)
            if parsed and (
                "recommended_drops" in parsed
                or "leakage_suspects" in parsed
                or "numeric_features" in parsed
            ):
                profile = parsed
                profile.setdefault("n_rows", int(len(df)))
                profile.setdefault("n_columns", int(len(df.columns)))
                profile.setdefault("target", target)
                profile.setdefault("recommended_drops", profile.get("leakage_suspects") or [])
                used_llm = True
                note = f"llm profile · {model}"
            else:
                note = f"llm unparsable; heuristic ({err or 'ok'})"
        else:
            note = f"{err or 'no llm'}; heuristic"

    return {
        "profile": profile,
        "steps": [
            {
                "node": "data_scientist",
                "note": note,
                "used_llm": used_llm,
                "model": model if used_llm else None,
                "output": profile,
            }
        ],
    }
`,
  },
  {
    id: "hypothesis",
    title: "node_hypothesis",
    hint: "Conceptual plan only \u2014 no concrete HPT numbers.",
    code: `    """Conceptual next experiment from DS profile + Judge feedback — no HPT numbers."""
    profile = state.get("profile") or {}
    brief = state.get("brief") or {}
    verdict = state.get("verdict") or {}
    history = list(brief.get("history") or (state.get("memory") or {}).get("history") or [])
    model = _resolve_model(state)

    plan = _heuristic_plan(profile, history, verdict)
    used_llm = False
    note = "heuristic plan"

    if llm_configured(model):
        system = (
            "You are the Hypothesis Generator only — not the Data Scientist and not the ML Engineer. "
            "Read the data-scientist profile and the latest judge verdict / lessons. "
            "Propose ONE conceptual research direction for the next trial. "
            "Do NOT invent concrete hyperparameter values, C/learning_rate/max_depth numbers, "
            "or a full ExperimentSpec — the ML Engineer owns HPT config. "
            "Return ONLY one JSON object with keys: "
            "direction (1-2 sentences: what should change conceptually), "
            "why (cite profile signals and/or judge observation), "
            "focus (one of: baseline_then_iterate|capacity_or_regularization|model_family_switch|feature_drops), "
            "respect_drops (string[] of columns to keep dropped — copy from profile when relevant), "
            "avoid_repeats (string[] of model families or ideas already tried). "
            "Stay conceptual: e.g. 'try a tree ensemble with less regularization' — never 'C=0.5'."
        )
        user = (
            f"profile={json.dumps(profile, default=str)}\\n"
            f"latest_verdict={json.dumps(verdict, default=str)}\\n"
            f"brief={json.dumps(brief, default=str)}\\n"
            f"recent_history={json.dumps(history[-5:], default=str)}\\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=500, temperature=0.4)
        if content:
            parsed = extract_json_object(content)
            if parsed and parsed.get("direction"):
                plan = {
                    "direction": parsed.get("direction"),
                    "why": parsed.get("why") or plan.get("why"),
                    "focus": parsed.get("focus") or plan.get("focus"),
                    "respect_drops": parsed.get("respect_drops")
                    if isinstance(parsed.get("respect_drops"), list)
                    else plan.get("respect_drops"),
                    "avoid_repeats": parsed.get("avoid_repeats")
                    if isinstance(parsed.get("avoid_repeats"), list)
                    else plan.get("avoid_repeats"),
                }
                used_llm = True
                note = f"live conceptual hypothesis · {model}"
            else:
                note = f"llm unparsable; heuristic ({err or 'ok'})"
        else:
            note = f"{err or 'no llm'}; heuristic"

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
`,
  },
  {
    id: "ml_engineer",
    title: "node_ml_engineer",
    hint: "Translate plan \u2192 ExperimentSpec, train/val, coerce/repair.",
    code: `    """Turn conceptual hypothesis into concrete HPT ExperimentSpec, then train/val."""
    df = pd.read_csv(state["dataset_path"])
    target = state["target_column"]
    profile = state.get("profile") or {}
    plan = dict(state.get("hypothesis") or {})
    brief = state.get("brief") or {}
    history = list(brief.get("history") or (state.get("memory") or {}).get("history") or [])
    prev_spec = dict(state.get("experiment_spec") or state.get("best_spec") or {})
    seed = int(state.get("seed") or 42)
    holdout_frac = float(state.get("holdout_frac") or 0.2)
    model_id = _resolve_model(state)

    spec = _heuristic_spec(profile, history, plan)
    used_llm = False
    repaired = False
    note = "heuristic HPT"

    default_drops = (
        plan.get("respect_drops")
        or profile.get("recommended_drops")
        or profile.get("leakage_suspects")
        or []
    )
    next_eid = f"exp-{len(history) + 1}"
    raw_llm: str | None = None

    if llm_configured(model_id):
        system = (
            "You are the ML Engineer only — not the Hypothesis Generator and not the Judge. "
            "The hypothesis agent already decided the conceptual direction. "
            "Your job: translate that plan into a concrete hyperparameter / training config. "
            "Return ONLY one JSON object matching this schema exactly: "
            f"{_SPEC_SCHEMA_HINT} "
            "model_family MUST be one of logistic_regression|random_forest|hist_gradient_boosting. "
            "hyperparameters MUST be a JSON object with concrete numbers for that family "
            "(C/max_iter OR n_estimators/max_depth OR learning_rate/max_iter). "
            "drop_columns is a string array. rationale is one sentence. "
            "No markdown fences, no commentary."
        )
        user = (
            f"hypothesis_plan={json.dumps(plan, default=str)}\\n"
            f"profile={json.dumps({k: profile.get(k) for k in ('recommended_drops', 'leakage_suspects', 'n_rows', 'target_rate')}, default=str)}\\n"
            f"prior_spec={json.dumps(prev_spec, default=str)}\\n"
            f"recent_history={json.dumps(history[-3:], default=str)}\\n"
            f"allowed_families={list(FAMILIES)}\\n"
            f"next_experiment_id={next_eid}\\n"
        )
        content, err = openrouter_chat(
            system, user, model=model_id, max_tokens=700, temperature=0.2, json_object=True
        )
        raw_llm = content
        coerced = _coerce_experiment_spec(
            extract_json_object(content or ""),
            experiment_id=next_eid,
            default_drops=default_drops,
        )
        if coerced is None and content and llm_configured(model_id):
            # One strict repair pass — common with Cursor prose wrapping JSON.
            fix_system = (
                "Convert the text into ONE valid ExperimentSpec JSON object. "
                f"Schema example: {_SPEC_SCHEMA_HINT} "
                f"model_family must be one of {list(FAMILIES)}. "
                "Output JSON only."
            )
            fix_user = (
                f"raw_model_output={content[:3500]}\\n"
                f"plan={json.dumps(plan, default=str)}\\n"
                f"next_experiment_id={next_eid}\\n"
            )
            content2, err2 = openrouter_chat(
                fix_system,
                fix_user,
                model=model_id,
                max_tokens=500,
                temperature=0.0,
                json_object=True,
            )
            raw_llm = content2 or content
            coerced = _coerce_experiment_spec(
                extract_json_object(content2 or ""),
                experiment_id=next_eid,
                default_drops=default_drops,
            )
            err = err2 or err
        if coerced:
            spec = coerced
            used_llm = True
            note = f"live HPT config · {model_id}"
        else:
            note = f"llm unparsable HPT; heuristic ({err or 'ok'})"

    err = _validate_spec(spec)
    if err and llm_configured(model_id):
        system = (
            "You are the ML Engineer repairing an invalid HPT ExperimentSpec. "
            f"Return ONLY JSON matching: {_SPEC_SCHEMA_HINT} "
            f"model_family must be one of {list(FAMILIES)}."
        )
        user = (
            f"error={err}\\n"
            f"spec={json.dumps(spec, default=str)}\\n"
            f"plan={json.dumps(plan, default=str)}\\n"
            f"raw_model_output={(raw_llm or '')[:2000]}\\n"
        )
        content, _llm_err = openrouter_chat(
            system, user, model=model_id, max_tokens=500, temperature=0.0, json_object=True
        )
        coerced = _coerce_experiment_spec(
            extract_json_object(content or ""),
            experiment_id=next_eid,
            default_drops=default_drops,
        )
        if coerced:
            spec = coerced
            used_llm = True
            repaired = True
            note = f"repaired HPT after: {err}"
            err = _validate_spec(spec)
    if err:
        spec = _repair_heuristic(spec, err)
        repaired = True
        note = f"heuristic repair after: {err}"
        err = _validate_spec(spec)

    cycle = int(state.get("cycle") or 0) + 1
    if err:
        result = {"status": "failed", "error": err, "validation_metrics": {}}
        return {
            "execution_result": result,
            "experiment_spec": spec,
            "cycle": cycle,
            "steps": [
                {
                    "node": "ml_engineer",
                    "note": note,
                    "status": "failed",
                    "repaired": repaired,
                    "used_llm": used_llm,
                    "experiment_id": spec.get("experiment_id"),
                    "model_family": spec.get("model_family"),
                    "spec": spec,
                    "output": {"experiment_spec": spec, "error": err},
                }
            ],
        }

    try:
        result = _fit_score(df, target, spec, seed, holdout_frac, on_holdout=False)
    except Exception as exc:  # noqa: BLE001
        if not repaired:
            spec = _repair_heuristic(spec, str(exc))
            repaired = True
            note = f"heuristic repair after run error: {exc}"
            try:
                result = _fit_score(df, target, spec, seed, holdout_frac, on_holdout=False)
            except Exception as exc2:  # noqa: BLE001
                result = {"status": "failed", "error": str(exc2), "validation_metrics": {}}
        else:
            result = {"status": "failed", "error": str(exc), "validation_metrics": {}}

    f1 = float((result.get("validation_metrics") or {}).get("f1") or 0)
    patch: dict = {
        "execution_result": result,
        "experiment_spec": spec,
        "cycle": cycle,
        "steps": [
            {
                "node": "ml_engineer",
                "note": note if result.get("status") != "succeeded" else f"{note} · f1={f1:.3f}",
                "f1": f1 if result.get("status") == "succeeded" else None,
                "status": result.get("status"),
                "repaired": repaired,
                "used_llm": used_llm,
                "experiment_id": spec.get("experiment_id"),
                "model_family": spec.get("model_family"),
                "validation_metrics": result.get("validation_metrics") or {},
                "duration_seconds": result.get("duration_seconds"),
                "spec": spec,
                "output": {
                    "experiment_spec": spec,
                    "execution_result": {
                        "status": result.get("status"),
                        "validation_metrics": result.get("validation_metrics"),
                        "error": result.get("error"),
                    },
                },
            }
        ],
    }
    if result.get("status") == "succeeded" and f1 > float(state.get("best_val_f1") or -1):
        patch["best_val_f1"] = f1
        patch["best_spec"] = spec
    return patch
`,
  },
  {
    id: "judge",
    title: "node_judge",
    hint: "Accept vs revise from val metrics (+ LLM observation).",
    code: `    """Verdict via OpenRouter; heuristic fallback."""
    result = state.get("execution_result") or {}
    spec = state.get("experiment_spec") or {}
    plan = state.get("hypothesis") or {}
    brief = state.get("brief") or {}
    target_score = float(state.get("target_score") or 0.8)
    model = _resolve_model(state)

    verdict = _heuristic_verdict(result, target_score)
    used_llm = False
    note = "heuristic"

    if llm_configured(model):
        system = (
            "You are the Judge only — not the Hypothesis Generator and not the ML Engineer. "
            "Decide from VALIDATION evidence only — never invent holdout scores, "
            "never rewrite hyperparameters. "
            "Return ONLY one JSON object with keys: "
            "action (accept|revise|reject), observation (1-2 sentences with the val F1), "
            "next_action (short conceptual instruction for the hypothesis agent — no HPT numbers). "
            "accept only if validation F1 meets or exceeds target_score; "
            "revise when under target but recoverable; reject for hopeless/broken runs."
        )
        user = (
            f"target_score={target_score}\\n"
            f"hypothesis_plan={json.dumps(plan, default=str)}\\n"
            f"spec={json.dumps(spec, default=str)}\\n"
            f"result={json.dumps(result, default=str)}\\n"
            f"brief={json.dumps(brief, default=str)}\\n"
        )
        content, err = openrouter_chat(system, user, model=model, max_tokens=500, temperature=0.1)
        if content:
            parsed = extract_json_object(content)
            if parsed and parsed.get("action") in {"accept", "revise", "reject"}:
                verdict = {
                    "action": parsed["action"],
                    "observation": parsed.get("observation") or verdict.get("observation"),
                    "next_action": parsed.get("next_action") or verdict.get("next_action"),
                }
                used_llm = True
                note = f"llm verdict · {model}"
            else:
                note = f"llm unparsable; heuristic ({err or 'ok'})"
        else:
            note = f"{err or 'no llm'}; heuristic"

    return {
        "verdict": verdict,
        "steps": [
            {
                "node": "judge",
                "note": note,
                "verdict": verdict,
                "used_llm": used_llm,
                "model": model if used_llm else None,
            }
        ],
    }
`,
  },
  {
    id: "memory",
    title: "node_memory_writer",
    hint: "Append cycle lesson into memory.",
    code: `    """Append this cycle's lesson so the next hypothesis can see history."""
    mem = dict(state.get("memory") or {"history": [], "findings": [], "lessons": []})
    hist = list(mem.get("history") or [])
    hist.append(
        {
            "cycle": state.get("cycle"),
            "hypothesis": state.get("hypothesis"),
            "spec": state.get("experiment_spec"),
            "model_family": (state.get("experiment_spec") or {}).get("model_family"),
            "f1": (state.get("execution_result") or {}).get("validation_metrics", {}).get("f1"),
            "verdict": state.get("verdict"),
        }
    )
    mem["history"] = hist
    lessons = list(mem.get("lessons") or [])
    lessons.append(str((state.get("verdict") or {}).get("observation") or ""))
    mem["lessons"] = lessons
    return {"memory": mem, "steps": [{"node": "memory_writer", "note": "filed lesson"}]}
`,
  },
  {
    id: "context",
    title: "node_context_builder",
    hint: "Brief for next hypothesis from memory.",
    code: `    """Build a short brief for the next hypothesis from recent memory."""
    mem = state.get("memory") or {}
    brief = {
        "history": mem.get("history") or [],
        "lessons": (mem.get("lessons") or [])[-3:],
    }
    return {"brief": brief, "steps": [{"node": "context_builder", "note": "next brief"}]}
`,
  },
  {
    id: "holdout",
    title: "node_holdout",
    hint: "Score best spec once on sealed holdout.",
    code: `    """Score the best spec ONCE on the sealed holdout (same seed as ml_engineer)."""
    df = pd.read_csv(state["dataset_path"])
    target = state["target_column"]
    spec = state.get("best_spec") or state.get("experiment_spec") or {}
    seed = int(state.get("seed") or 42)
    holdout_frac = float(state.get("holdout_frac") or 0.2)
    if _validate_spec(spec):
        spec = _repair_heuristic(dict(spec), "invalid best_spec")
    metrics = _fit_score(df, target, spec, seed, holdout_frac, on_holdout=True)
    return {
        "holdout_metrics": metrics,
        "stop_reason": "finalize",
        "steps": [{"node": "holdout_eval", "note": "sealed holdout", "metrics": metrics}],
    }
`,
  },
  {
    id: "router",
    title: "route_after_judge",
    hint: "Must return \"holdout\" or \"memory\" (keys in conditional_edges).",
    code: `    """Router = plain code (not an LLM)."""
    action = str((state.get("verdict") or {}).get("action") or "stop")
    cycle = int(state.get("cycle") or 0)
    max_cycles = int(state.get("max_cycles") or 3)
    if action == "accept":
        return "holdout"
    if action == "revise" and cycle < max_cycles:
        return "memory"
    return "holdout"
`,
  },
]

/** Wiring after `g = StateGraph(SimpleLoopState)` — includes the reference comment block. */
export const BUILD_GRAPH_SNIPPET = `# ---------------------------------------------------------------------------
# GRAPH WIRING
# StateGraph = the canvas.
# add_node(name, fn) = put a box on the canvas.
# add_edge(a, b)     = always go a → b after a finishes.
# add_conditional_edges = ask a router function which named edge to take.
# compile()          = freeze the graph into a runnable app (invoke / stream).
# ---------------------------------------------------------------------------
g.add_node("data_scientist", node_data_scientist)
g.add_node("hypothesis_generator", node_hypothesis)
g.add_node("ml_engineer", node_ml_engineer)
g.add_node("judge", node_judge)
g.add_node("memory_writer", node_memory_writer)
g.add_node("context_builder", node_context_builder)
g.add_node("holdout_eval", node_holdout)

g.add_edge(START, "data_scientist")
g.add_edge("data_scientist", "hypothesis_generator")
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
g.add_edge("memory_writer", "context_builder")
g.add_edge("context_builder", "hypothesis_generator")  # loop back
g.add_edge("holdout_eval", END)
return g.compile()
`

