"""Parse and validate arbitrary tabular CSVs (Kaggle-style) for classification."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd

MAX_ROWS = 20_000
MIN_ROWS = 40
MAX_CLASSES = 50


def read_csv_bytes(raw: bytes) -> pd.DataFrame:
    """Best-effort parse of Kaggle CSVs: encodings + common separators."""
    last_err: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t", "|"):
            try:
                df = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=sep)
                if df.shape[1] >= 2 and len(df) > 0:
                    return df
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding, sep=None, engine="python")
            if df.shape[1] >= 2 and len(df) > 0:
                return df
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise ValueError(f"could not parse CSV ({last_err})")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip() for c in out.columns]
    # Drop fully empty columns (common in exports).
    out = out.dropna(axis=1, how="all")
    return out


def resolve_target_column(df: pd.DataFrame, target_column: str) -> str:
    if target_column in df.columns:
        return target_column
    lowered = {c.lower(): c for c in df.columns}
    if target_column.lower() in lowered:
        return lowered[target_column.lower()]
    raise ValueError(
        f"target column {target_column!r} not in dataset; columns={list(df.columns)[:40]}"
    )


def prepare_classification_frame(
    df: pd.DataFrame,
    target_column: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drop NA targets, enforce discrete labels, optionally downsample huge files."""
    target = resolve_target_column(df, target_column)
    work = normalize_columns(df)
    target = resolve_target_column(work, target)

    before = len(work)
    work = work.dropna(subset=[target]).copy()
    dropped_na = before - len(work)
    if len(work) < MIN_ROWS:
        raise ValueError(
            f"need at least {MIN_ROWS} rows with a non-null target; got {len(work)}"
        )

    # Cast bool / object targets to stable string labels for sklearn.
    if pd.api.types.is_bool_dtype(work[target]):
        work[target] = work[target].astype(int)
    elif not pd.api.types.is_numeric_dtype(work[target]):
        work[target] = work[target].astype(str).str.strip()

    n_classes = int(work[target].nunique(dropna=True))
    if n_classes < 2:
        raise ValueError("classification target must have at least 2 classes")
    if n_classes > MAX_CLASSES:
        raise ValueError(
            f"target looks continuous or has too many classes ({n_classes}); "
            f"expected a categorical target with ≤ {MAX_CLASSES} classes"
        )

    sampled = False
    if len(work) > MAX_ROWS:
        # Fixed-seed downsample so demos stay snappy over JSON splits.
        parts: list[pd.DataFrame] = []
        for _, group in work.groupby(target, sort=False):
            n = max(1, int(round(len(group) * (MAX_ROWS / len(work)))))
            parts.append(group.sample(n=min(n, len(group)), random_state=42))
        work = pd.concat(parts, ignore_index=True)
        if len(work) > MAX_ROWS:
            work = work.sample(n=MAX_ROWS, random_state=42).reset_index(drop=True)
        sampled = True

    notes = {
        "dropped_null_target_rows": int(dropped_na),
        "n_classes": n_classes,
        "sampled_to_max_rows": sampled,
        "max_rows": MAX_ROWS,
        "resolved_target_column": target,
    }
    return work, notes


def identifier_columns(columns: list[str], target: str) -> list[str]:
    ids: list[str] = []
    for c in columns:
        if c == target:
            continue
        low = c.lower().replace(" ", "")
        if low in {"id", "index", "idx"} or low.endswith("id") or low.endswith("_id"):
            ids.append(c)
    return ids


def can_stratify(y: pd.Series) -> bool:
    counts = y.value_counts()
    return bool(len(counts) >= 2 and counts.min() >= 2)
