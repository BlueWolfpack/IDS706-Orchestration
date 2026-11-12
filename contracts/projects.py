"""Project and training-session registry contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SessionMode = Literal["live", "mock", "replay"]
SessionStatus = Literal["created", "running", "completed", "failed", "paused", "reset"]


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""


class TrainingSessionRecord(BaseModel):
    session_id: str
    project_id: str
    status: SessionStatus = "created"
    mode: SessionMode = "live"
    mock: bool = False
    replay: bool = False
    dataset_filename: str | None = None
    dataset_id: str | None = None
    target_column: str
    task_type: str = "classification"
    metric: str = "f1"
    target_score: float = 0.7
    experiment_budget: int = 5
    experiments_used: int = 0
    research_strategy: str = "model_search"
    fixed_model_family: str | None = None
    per_trial_timeout_seconds: int = 120
    best_val_score: float | None = None
    holdout_score: float | None = None
    stop_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    description: str = ""
    created_at: datetime
    updated_at: datetime
    session_count: int = 0
    last_session_at: datetime | None = None
    best_val_score: float | None = None


class ProjectDetail(ProjectSummary):
    sessions: list[TrainingSessionRecord] = Field(default_factory=list)


class PriorDataset(BaseModel):
    """A CSV previously used on this project (or available in the datasets catalog)."""

    filename: str
    target_column: str | None = None
    times_used: int = 1
    last_used_at: datetime | None = None
    source: Literal["project_history", "catalog"] = "project_history"
