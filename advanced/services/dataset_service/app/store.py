"""Own-store for datasets. Holdout rows never leave this process except as a score."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from services.dataset_service.app.csv_ingest import (
    can_stratify,
    identifier_columns,
    prepare_classification_frame,
    read_csv_bytes,
)

SPLIT_SEED = 42
HOLDOUT_FRAC = 0.2
VAL_FRAC_OF_REMAINDER = 0.25  # → ~60% train / 20% val / 20% holdout


@dataclass
class DatasetRecord:
    dataset_id: str
    filename: str
    target_column: str
    task_type: str
    n_rows: int
    n_columns: int
    feature_columns: list[str]
    holdout_evaluated: bool = False
    session_holdout_keys: set[str] = field(default_factory=set)
    ingest_notes: dict[str, Any] = field(default_factory=dict)


class DatasetStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._meta: dict[str, DatasetRecord] = {}
        self._lock = threading.Lock()

    def _dir(self, dataset_id: str) -> Path:
        return self.root / dataset_id

    def _split(self, df: pd.DataFrame, target: str, task_type: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        stratify_full = df[target] if task_type == "classification" and can_stratify(df[target]) else None
        train_val, holdout = train_test_split(
            df,
            test_size=HOLDOUT_FRAC,
            random_state=SPLIT_SEED,
            stratify=stratify_full,
        )
        stratify_tv = (
            train_val[target]
            if task_type == "classification" and can_stratify(train_val[target])
            else None
        )
        train, validation = train_test_split(
            train_val,
            test_size=VAL_FRAC_OF_REMAINDER,
            random_state=SPLIT_SEED,
            stratify=stratify_tv,
        )
        return train, validation, holdout

    def create_from_csv(
        self,
        raw: bytes,
        filename: str,
        target_column: str,
        task_type: str = "classification",
    ) -> DatasetRecord:
        if task_type != "classification":
            raise ValueError(
                "only classification is supported in this lab; pick a discrete target column"
            )

        dataset_id = f"ds-{uuid.uuid4().hex[:10]}"
        d = self._dir(dataset_id)
        d.mkdir(parents=True, exist_ok=True)
        csv_path = d / "source.csv"
        csv_path.write_bytes(raw)

        parsed = read_csv_bytes(raw)
        df, notes = prepare_classification_frame(parsed, target_column)
        target = str(notes["resolved_target_column"])

        train, validation, holdout = self._split(df, target, task_type)

        train.to_parquet(d / "train.parquet", index=False)
        validation.to_parquet(d / "validation.parquet", index=False)
        # Sealed: never exposed via public HTTP.
        holdout.to_parquet(d / "holdout.parquet", index=False)

        features = [c for c in df.columns if c != target]
        rec = DatasetRecord(
            dataset_id=dataset_id,
            filename=filename,
            target_column=target,
            task_type=task_type,
            n_rows=len(df),
            n_columns=len(df.columns),
            feature_columns=features,
            ingest_notes=notes,
        )
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "target_column": target,
                    "task_type": task_type,
                    "n_rows": rec.n_rows,
                    "n_columns": rec.n_columns,
                    "feature_columns": features,
                    "split_seed": SPLIT_SEED,
                    "ingest_notes": notes,
                },
                indent=2,
            )
        )
        with self._lock:
            self._meta[dataset_id] = rec
        return rec

    def get(self, dataset_id: str) -> DatasetRecord | None:
        with self._lock:
            if dataset_id in self._meta:
                return self._meta[dataset_id]
        meta_path = self._dir(dataset_id) / "meta.json"
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text())
        rec = DatasetRecord(
            dataset_id=data["dataset_id"],
            filename=data["filename"],
            target_column=data["target_column"],
            task_type=data["task_type"],
            n_rows=data["n_rows"],
            n_columns=data["n_columns"],
            feature_columns=data["feature_columns"],
            ingest_notes=dict(data.get("ingest_notes") or {}),
        )
        with self._lock:
            self._meta[dataset_id] = rec
        return rec

    def read_split(self, dataset_id: str, name: str) -> pd.DataFrame:
        if name not in {"train", "validation"}:
            raise PermissionError("only train and validation splits are readable")
        path = self._dir(dataset_id) / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(name)
        return pd.read_parquet(path)

    def profile_view(self, dataset_id: str) -> dict[str, Any]:
        rec = self.get(dataset_id)
        if rec is None:
            raise FileNotFoundError(dataset_id)
        train = self.read_split(dataset_id, "train")
        val = self.read_split(dataset_id, "validation")
        combined = pd.concat([train, val], ignore_index=True)
        target = rec.target_column
        class_balance = None
        if rec.task_type == "classification":
            rates = combined[target].value_counts(normalize=True).to_dict()
            class_balance = {str(k): float(v) for k, v in rates.items()}
        identifiers = identifier_columns(list(combined.columns), target)
        return {
            "dataset_id": dataset_id,
            "filename": rec.filename,
            "n_rows_visible": int(len(combined)),
            "n_columns": rec.n_columns,
            "target_column": target,
            "task_type": rec.task_type,
            "class_balance": class_balance,
            "identifier_columns": identifiers,
            "feature_columns": rec.feature_columns,
            "ingest_notes": rec.ingest_notes,
            "note": "train+validation only; holdout is sealed",
            "mock": False,
        }

    def evaluate_holdout(
        self,
        dataset_id: str,
        session_id: str,
        model_path: str,
        metric: str = "f1",
    ) -> dict[str, Any]:
        rec = self.get(dataset_id)
        if rec is None:
            raise FileNotFoundError(dataset_id)
        # One evaluate per session (teaching rule: sealed holdout opened once).
        with self._lock:
            if any(k.startswith(f"{session_id}:") for k in rec.session_holdout_keys):
                raise RuntimeError("holdout already evaluated for this session")
        key = f"{session_id}:{dataset_id}"

        holdout_path = self._dir(dataset_id) / "holdout.parquet"
        if not holdout_path.exists():
            raise FileNotFoundError("holdout")
        holdout = pd.read_parquet(holdout_path)
        pipe = joblib.load(model_path)
        identifiers = identifier_columns(list(holdout.columns), rec.target_column)
        drop_cols = [rec.target_column, *identifiers]
        X = holdout.drop(columns=[c for c in drop_cols if c in holdout.columns])
        y = holdout[rec.target_column]
        pred = pipe.predict(X)

        if metric == "f1":
            average = "binary" if int(pd.Series(y).nunique()) <= 2 else "weighted"
            try:
                score = float(f1_score(y, pred, average=average, zero_division=0))
            except ValueError:
                score = float(f1_score(y, pred, average="weighted", zero_division=0))
        elif metric == "accuracy":
            score = float(accuracy_score(y, pred))
        else:
            raise ValueError(f"unsupported metric {metric}")

        with self._lock:
            rec.session_holdout_keys.add(key)
            rec.holdout_evaluated = True

        return {
            "dataset_id": dataset_id,
            "session_id": session_id,
            "metric": metric,
            "score": score,
            "n_holdout": int(len(holdout)),
            "mock": False,
            "note": "holdout rows are not returned",
        }
