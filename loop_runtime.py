"""Shared LLM + train helpers for solution/langgraph / lab/langgraph (not a student exercise).

Cursor SDK + OpenRouter chat, JSON coerce, sklearn fit helpers, and heuristics.
Imported by both graphs so the classroom guide only pastes node bodies + wiring.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

REPO = Path(__file__).resolve().parent

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3.5-lightning:free",
)
FAMILIES = (
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
)

# ---------------------------------------------------------------------------
# LLM (Cursor SDK + OpenRouter)
# ---------------------------------------------------------------------------
def _is_cursor_model(model: str | None) -> bool:
    m = (model or "").strip().lower()
    return m.startswith("cursor/") or m in {"composer-2.5", "composer-2", "composer"}


def llm_configured(model: str | None = None) -> bool:
    """True when the selected provider has a key (or either key if model unknown)."""
    if _is_cursor_model(model):
        return bool(os.getenv("CURSOR_API_KEY", "").strip())
    if model and str(model).strip():
        return bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    return bool(
        os.getenv("OPENROUTER_API_KEY", "").strip() or os.getenv("CURSOR_API_KEY", "").strip()
    )


def _resolve_model(state: Mapping[str, Any] | None = None) -> str:
    if state:
        m = (state.get("model") or "").strip()
        if m:
            return m
    return (os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL).strip()


def cursor_chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
) -> tuple[str | None, str | None]:
    """Cursor Agent SDK prompt. Returns (content, error)."""
    key = os.getenv("CURSOR_API_KEY", "").strip()
    if not key:
        return None, "CURSOR_API_KEY not set"
    mid = (model or "composer-2.5").strip()
    if mid.startswith("cursor/"):
        mid = mid.split("/", 1)[1]
    try:
        from cursor_sdk import Agent, AgentOptions, LocalAgentOptions

        result = Agent.prompt(
            f"{system}\n\nRespond with ONLY a JSON object.\n\n{user}",
            AgentOptions(
                api_key=key,
                model=mid,
                local=LocalAgentOptions(cwd=str(REPO)),
            ),
        )
        text = getattr(result, "result", None) or str(result)
        if not isinstance(text, str) or not text.strip():
            return None, "empty cursor sdk content"
        return text.strip(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"cursor sdk: {exc}"


def openrouter_chat(
    system: str,
    user: str,
    *,
    model: str | None = None,
    max_tokens: int = 1200,
    temperature: float = 0.2,
    retries: int = 2,
    json_object: bool = False,
) -> tuple[str | None, str | None]:
    """Chat via Cursor SDK (cursor/*) or OpenRouter. Returns (content, error)."""
    chosen = (model or "").strip() or DEFAULT_MODEL
    if json_object:
        system = (
            system.rstrip()
            + "\n\nRespond with ONLY one valid JSON object. No markdown, no prose."
        )
    if _is_cursor_model(chosen):
        content, err = cursor_chat(system, user, model=chosen)
        if err:
            return None, f"[{chosen}] {err}"
        return content, None

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None, f"[{chosen}] OPENROUTER_API_KEY not set"
    body: dict[str, Any] = {
        "model": chosen,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        # Reasoning models otherwise burn the budget before emitting JSON.
        "reasoning": {"enabled": False},
    }
    if json_object:
        body["response_format"] = {"type": "json_object"}
    last_err: str | None = None
    for _ in range(max(1, retries)):
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://localhost/automl-research-lab",
                "X-Title": "Simple Research Loop",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            last_err = f"HTTP {exc.code}: {detail}"
            continue
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)
            continue

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            last_err = f"unexpected response: {str(data)[:300]}"
            continue

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            reasoning = message.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                content = reasoning
            else:
                last_err = "empty model content"
                body["max_tokens"] = min(int(body["max_tokens"]) + 400, 2400)
                continue
        return content.strip(), None

    return None, f"[{chosen}] {last_err or 'openrouter failed'}"


def extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()

    def _as_dict(obj: Any) -> dict[str, Any] | None:
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            return obj[0]
        return None

    try:
        return _as_dict(json.loads(text))
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return _as_dict(json.loads(text[start : end + 1]))
        except json.JSONDecodeError:
            return None
    return None


_FAMILY_ALIASES = {
    "logistic": "logistic_regression",
    "logisticregression": "logistic_regression",
    "logreg": "logistic_regression",
    "lr": "logistic_regression",
    "rf": "random_forest",
    "randomforest": "random_forest",
    "extra_trees": "random_forest",
    "extratrees": "random_forest",
    "hgb": "hist_gradient_boosting",
    "histgradientboosting": "hist_gradient_boosting",
    "gradient_boosting": "hist_gradient_boosting",
    "gbdt": "hist_gradient_boosting",
}


def _normalize_family(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if raw in FAMILIES:
        return raw
    key = raw.lower().replace("-", "_").replace(" ", "_")
    if key in FAMILIES:
        return key
    return _FAMILY_ALIASES.get(key.replace("_", "")) or _FAMILY_ALIASES.get(key)


def _coerce_experiment_spec(
    raw: dict[str, Any] | None,
    *,
    experiment_id: str,
    default_drops: list | None = None,
) -> dict[str, Any] | None:
    """Normalize LLM JSON into a valid ExperimentSpec, or None."""
    if not isinstance(raw, dict):
        return None
    obj = raw
    for nest in ("experiment_spec", "spec", "config", "experiment"):
        nested = obj.get(nest)
        if isinstance(nested, dict) and (
            "model_family" in nested or "hyperparameters" in nested or "family" in nested
        ):
            obj = nested
            break

    family = _normalize_family(obj.get("model_family") or obj.get("family") or obj.get("model"))
    if family is None:
        return None

    hp = obj.get("hyperparameters") or obj.get("params") or obj.get("hp") or {}
    if not isinstance(hp, dict):
        hp = {}

    drops = obj.get("drop_columns")
    if drops is None:
        drops = obj.get("drops")
    if not isinstance(drops, list):
        drops = list(default_drops or [])

    eid = obj.get("experiment_id") or obj.get("id") or experiment_id
    rationale = obj.get("rationale") or obj.get("reason") or obj.get("why") or ""
    return {
        "experiment_id": str(eid),
        "model_family": family,
        "hyperparameters": hp,
        "drop_columns": [str(c) for c in drops],
        "rationale": str(rationale),
    }


_SPEC_SCHEMA_HINT = (
    '{"experiment_id":"exp-1","model_family":"random_forest",'
    '"hyperparameters":{"n_estimators":200,"max_depth":8},'
    '"drop_columns":[],"rationale":"one sentence"}'
)


# ---------------------------------------------------------------------------
# TRAIN HELPERS (shared by ml_engineer + holdout)
# ---------------------------------------------------------------------------
def _validate_spec(spec: dict) -> str | None:
    if not isinstance(spec, dict):
        return "spec must be object"
    if spec.get("model_family") not in FAMILIES:
        return f"model_family must be one of {sorted(FAMILIES)}"
    hp = spec.get("hyperparameters")
    if hp is not None and not isinstance(hp, dict):
        return "hyperparameters must be object"
    return None


def _repair_heuristic(spec: dict, error: str) -> dict:
    fixed = dict(spec)
    fixed["hyperparameters"] = dict(spec.get("hyperparameters") or {})
    fam = fixed.get("model_family")
    if fam not in FAMILIES:
        fixed["model_family"] = "random_forest"
        fam = "random_forest"
    if fam == "logistic_regression":
        fixed["hyperparameters"] = {"C": 1.0, "max_iter": 400}
    elif fam == "hist_gradient_boosting":
        fixed["hyperparameters"] = {"learning_rate": 0.1, "max_iter": 100}
    else:
        fixed["model_family"] = "random_forest"
        fixed["hyperparameters"] = {"n_estimators": 100, "max_depth": 6}
    fixed["rationale"] = f"repaired after: {error[:120]}"
    return fixed


def _build_model(family: str, hp: dict):
    if family == "logistic_regression":
        return LogisticRegression(
            C=float(hp.get("C", 1.0)),
            max_iter=int(hp.get("max_iter", 300)),
            class_weight="balanced",
        )
    if family == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            learning_rate=float(hp.get("learning_rate", 0.1)),
            max_iter=int(hp.get("max_iter", 100)),
        )
    return RandomForestClassifier(
        n_estimators=int(hp.get("n_estimators", 100)),
        max_depth=hp.get("max_depth", 6),
        random_state=42,
        class_weight="balanced",
    )


def _fit_score(
    df: pd.DataFrame,
    target: str,
    spec: dict,
    seed: int,
    holdout_frac: float,
    *,
    on_holdout: bool,
) -> dict:
    y = df[target]
    drops = [c for c in (spec.get("drop_columns") or []) if c in df.columns and c != target]
    X = df.drop(columns=[target, *drops], errors="ignore")
    strat = y if y.nunique() > 1 else None
    X_tmp, X_hold, y_tmp, y_hold = train_test_split(
        X, y, test_size=holdout_frac, random_state=seed, stratify=strat
    )
    if on_holdout:
        X_train, y_train, X_eval, y_eval = X_tmp, y_tmp, X_hold, y_hold
    else:
        X_train, X_eval, y_train, y_eval = train_test_split(
            X_tmp,
            y_tmp,
            test_size=0.25,
            random_state=seed,
            stratify=y_tmp if y_tmp.nunique() > 1 else None,
        )

    num_cols = [c for c in X_train.columns if pd.api.types.is_numeric_dtype(X_train[c])]
    cat_cols = [c for c in X_train.columns if c not in num_cols]
    pre = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), num_cols),
            (
                "cat",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="most_frequent")),
                        ("oh", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                cat_cols,
            ),
        ]
    )
    family = str(spec.get("model_family") or "logistic_regression")
    model = _build_model(family, dict(spec.get("hyperparameters") or {}))
    pipe = Pipeline([("pre", pre), ("clf", model)])
    t0 = time.time()
    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_eval)
    duration = time.time() - t0
    metrics = {
        "f1": float(f1_score(y_eval, pred, zero_division=0)),
        "accuracy": float(accuracy_score(y_eval, pred)),
    }
    if on_holdout:
        metrics["n_holdout"] = int(len(X_eval))
        return metrics
    return {
        "status": "succeeded",
        "experiment_id": spec.get("experiment_id"),
        "model_family": family,
        "hyperparameters": spec.get("hyperparameters") or {},
        "drop_columns": drops,
        "validation_metrics": metrics,
        "duration_sec": round(duration, 3),
        "duration_seconds": round(duration, 3),
        "n_train": int(len(X_train)),
        "n_val": int(len(X_eval)),
        "n_holdout": int(len(X_hold)),
    }


def _heuristic_profile(df: pd.DataFrame, target: str) -> dict:
    cols = list(df.columns)
    leakage = [
        c
        for c in cols
        if c != target
        and (
            c.lower() in {"passengerid", "name", "ticket", "cabin", "id", "timestamp", "fraud_probability"}
            or c.lower().endswith("_id")
        )
    ]
    num = [c for c in cols if c != target and c not in leakage and pd.api.types.is_numeric_dtype(df[c])]
    cat = [c for c in cols if c != target and c not in num and c not in leakage]
    return {
        "n_rows": int(len(df)),
        "n_columns": int(len(cols)),
        "target": target,
        "target_rate": float(df[target].mean())
        if target in df and pd.api.types.is_numeric_dtype(df[target])
        else None,
        "numeric_features": num,
        "categorical_features": cat,
        "leakage_suspects": leakage,
        "recommended_drops": leakage,
        "notes": [
            "Heuristic profile (OpenRouter unavailable).",
            "Drop id-like / high-cardinality text before modeling.",
        ],
    }


def _heuristic_plan(profile: dict, history: list, verdict: dict | None) -> dict:
    """Conceptual next step only — no concrete HPT numbers."""
    tried = []
    for h in history:
        if not isinstance(h, dict):
            continue
        fam = h.get("model_family")
        if not fam and isinstance(h.get("spec"), dict):
            fam = h["spec"].get("model_family")
        if fam:
            tried.append(fam)
    obs = str((verdict or {}).get("observation") or "")
    notes = profile.get("notes") if isinstance(profile.get("notes"), list) else []
    why = obs or (notes[0] if notes else "Use profile leakage flags, target rate, and judge feedback.")
    drops = list(profile.get("recommended_drops") or profile.get("leakage_suspects") or [])
    if obs and "below" in obs.lower():
        direction = "Increase model capacity or relax regularization; prior val F1 was under target."
        focus = "capacity_or_regularization"
    elif tried:
        direction = f"Switch modeling approach — already tried: {', '.join(dict.fromkeys(tried))}."
        focus = "model_family_switch"
    else:
        direction = "Start with a simple linear baseline, drop leakage-prone columns, then iterate."
        focus = "baseline_then_iterate"
    return {
        "direction": direction,
        "why": why,
        "focus": focus,
        "respect_drops": drops,
        "avoid_repeats": list(dict.fromkeys(tried)),
    }


def _heuristic_spec(profile: dict, history: list, plan: dict | None = None) -> dict:
    """Concrete ExperimentSpec / HPT — used when ML-engineer LLM is unavailable."""
    tried = {h.get("model_family") for h in history if isinstance(h, dict)}
    for h in history:
        if isinstance(h, dict) and isinstance(h.get("spec"), dict):
            tried.add(h["spec"].get("model_family"))
    focus = str((plan or {}).get("focus") or "")
    if focus == "model_family_switch":
        family = next((f for f in FAMILIES if f not in tried), "random_forest")
    elif focus == "capacity_or_regularization" and "logistic_regression" in tried:
        family = "logistic_regression"
    else:
        family = next((f for f in FAMILIES if f not in tried), "random_forest")
    n = len(history)
    if family == "logistic_regression":
        # stronger C when asking for more capacity
        cs = [0.25, 0.5, 1.0, 2.0, 4.0] if "capacity" in focus else [0.25, 0.5, 1.0, 2.0]
        hp = {"C": cs[n % len(cs)], "max_iter": 300}
    elif family == "hist_gradient_boosting":
        hp = {"learning_rate": [0.05, 0.1, 0.15][n % 3], "max_iter": 80 + 20 * (n % 3)}
    else:
        hp = {"n_estimators": 80 + 40 * (n % 4), "max_depth": [3, 5, 8, 12][n % 4]}
    drops = list(
        (plan or {}).get("respect_drops")
        or profile.get("recommended_drops")
        or profile.get("leakage_suspects")
        or []
    )
    return {
        "experiment_id": f"exp-{n + 1}",
        "model_family": family,
        "hyperparameters": hp,
        "drop_columns": drops,
        "rationale": f"heuristic HPT from plan focus={focus or 'default'}: {family}",
    }


def _heuristic_verdict(result: dict, target_score: float) -> dict:
    status = result.get("status")
    f1 = float((result.get("validation_metrics") or {}).get("f1") or 0)
    if status != "succeeded":
        return {
            "action": "revise",
            "observation": f"run failed: {result.get('error')}",
            "next_action": "propose next experiment",
        }
    if f1 >= target_score:
        return {
            "action": "accept",
            "observation": f"val f1 {f1:.3f} meets target {target_score:.2f}",
            "next_action": "finalize",
        }
    return {
        "action": "revise",
        "observation": f"val f1 {f1:.3f} below target {target_score:.2f}",
        "next_action": "propose next experiment",
    }

