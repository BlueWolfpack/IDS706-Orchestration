"""Lead-agent outputs and orchestrator research state."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VerdictAction(str, Enum):
    REVISE = "revise"
    REJECT = "reject"
    ACCEPT = "accept"
    STOP = "stop"


class DataProfile(BaseModel):
    dataset_id: str
    n_rows: int
    n_columns: int
    task_type: str
    target_column: str
    class_balance: dict[str, float] | None = None
    identifier_columns: list[str] = Field(default_factory=list)
    leakage_flags: list[str] = Field(default_factory=list)
    feature_notes: list[str] = Field(default_factory=list)
    mock: bool = False


class ExperimentSpec(BaseModel):
    experiment_id: str
    session_id: str
    model_family: str
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    novelty_ok: bool = True
    mock: bool = False


class ExecutionResult(BaseModel):
    experiment_id: str
    status: str  # succeeded | failed | timeout
    train_metrics: dict[str, float] = Field(default_factory=dict)
    validation_metrics: dict[str, float] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    retry_count: int = 0
    timeout_status: str | None = None
    mock: bool = False


class Verdict(BaseModel):
    experiment_id: str
    action: VerdictAction
    observation: str = ""
    hypothesis: str = ""
    next_action: str = ""
    overfitting_risk: str | None = None
    mock: bool = False


class ResearchState(BaseModel):
    """Orchestrator graph state. Large artifacts live outside and are referenced by id."""

    session_id: str
    dataset_id: str | None = None
    target_column: str | None = None
    task_type: str | None = None
    metric: str | None = None
    target_score: float | None = None
    experiment_budget: int = 10
    data_profile: DataProfile | None = None
    proposed_experiment: ExperimentSpec | None = None
    experiment_history: list[ExecutionResult] = Field(default_factory=list)
    latest_result: ExecutionResult | None = None
    judge_verdict: Verdict | None = None
    best_experiment_id: str | None = None
    experiment_count: int = 0
    retry_count: int = 0
    status: str = "created"
    stop_reason: str | None = None
