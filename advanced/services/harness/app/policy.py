"""Single source of truth for experiment limits (teaching: every limit lives here)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Policy(BaseModel):
    max_experiments: int = 10
    max_retries_per_experiment: int = 3
    per_trial_timeout_seconds: int = 120
    wall_clock_budget_seconds: int = 900
    allowed_model_families: list[str] = Field(
        default_factory=lambda: [
            "logistic_regression",
            "random_forest",
            "hist_gradient_boosting",
            "xgboost",  # alias → HistGradientBoostingClassifier
        ]
    )
    fixed_split_seed: int = 42
    require_pipeline: bool = True
    forbid_holdout_access: bool = True
    mock: bool = False


POLICY = Policy()


def get_policy() -> dict:
    return POLICY.model_dump()
