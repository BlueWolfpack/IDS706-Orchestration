"""Deterministic sklearn backends. No model-written code."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


def build_estimator(model_family: str, hyperparameters: dict[str, Any]):
    if model_family == "logistic_regression":
        return LogisticRegression(
            max_iter=int(hyperparameters.get("max_iter", 200)),
            C=float(hyperparameters.get("C", 1.0)),
            class_weight=hyperparameters.get("class_weight"),
            random_state=42,
        )
    if model_family == "random_forest":
        max_depth = hyperparameters.get("max_depth")
        if max_depth is not None and int(max_depth) < 1:
            raise ValueError("max_depth must be null or >= 1")
        return RandomForestClassifier(
            n_estimators=int(hyperparameters.get("n_estimators", 100)),
            max_depth=None if max_depth is None else int(max_depth),
            class_weight=hyperparameters.get("class_weight"),
            random_state=42,
            n_jobs=1,
        )
    # xgboost is a teaching alias for HistGradientBoosting (no extra dep).
    if model_family in {"hist_gradient_boosting", "xgboost"}:
        return HistGradientBoostingClassifier(
            learning_rate=float(hyperparameters.get("learning_rate", 0.1)),
            max_iter=int(hyperparameters.get("max_iter", 100)),
            l2_regularization=float(hyperparameters.get("l2_regularization", 0.0)),
            random_state=42,
        )
    raise ValueError(f"unsupported model_family {model_family}")


def build_pipeline(X: pd.DataFrame, model_family: str, hyperparameters: dict[str, Any]) -> Pipeline:
    num_cols = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    cat_cols = [c for c in X.columns if c not in num_cols]
    transformers: list[tuple[str, Any, list[str]]] = []
    if num_cols:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler()),
                    ]
                ),
                num_cols,
            )
        )
    if cat_cols:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("oh", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                cat_cols,
            )
        )
    if not transformers:
        raise ValueError("no usable feature columns after dropping identifiers/target")
    pre = ColumnTransformer(transformers=transformers, remainder="drop")
    return Pipeline([("pre", pre), ("model", build_estimator(model_family, hyperparameters))])


def score_predictions(y_true, y_pred) -> dict[str, float]:
    y_true = pd.Series(y_true)
    n_classes = int(y_true.nunique())
    average = "binary" if n_classes <= 2 else "weighted"
    try:
        f1 = float(f1_score(y_true, y_pred, average=average, zero_division=0))
        precision = float(precision_score(y_true, y_pred, average=average, zero_division=0))
        recall = float(recall_score(y_true, y_pred, average=average, zero_division=0))
    except ValueError:
        f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
        precision = float(precision_score(y_true, y_pred, average="weighted", zero_division=0))
        recall = float(recall_score(y_true, y_pred, average="weighted", zero_division=0))
    return {
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "n_classes": float(n_classes),
    }


def _coerce_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            # Mixed object columns: keep as categorical strings.
            out[c] = out[c].astype(str).replace({"nan": np.nan, "None": np.nan, "": np.nan})
    return out


def run_trial(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    target: str,
    model_family: str,
    hyperparameters: dict[str, Any],
    drop_columns: list[str] | None = None,
) -> tuple[Pipeline, dict[str, float], dict[str, float], float]:
    drop = set(drop_columns or [])
    drop.add(target)
    X_train = _coerce_features(train.drop(columns=[c for c in drop if c in train.columns]))
    y_train = train[target]
    X_val = _coerce_features(validation.drop(columns=[c for c in drop if c in validation.columns]))
    y_val = validation[target]

    # Align columns across splits.
    shared = [c for c in X_train.columns if c in X_val.columns]
    if not shared:
        # Extremely narrow CSV: keep a constant so the pipeline can still fit.
        X_train = X_train.copy()
        X_val = X_val.copy()
        X_train["_const"] = 1.0
        X_val["_const"] = 1.0
        shared = ["_const"]
    X_train = X_train[shared]
    X_val = X_val[shared]

    pipe = build_pipeline(X_train, model_family, hyperparameters)
    t0 = time.perf_counter()
    pipe.fit(X_train, y_train)
    duration = time.perf_counter() - t0
    train_metrics = score_predictions(y_train, pipe.predict(X_train))
    val_metrics = score_predictions(y_val, pipe.predict(X_val))
    return pipe, train_metrics, val_metrics, duration
