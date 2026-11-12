"""Gateway session command contracts."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


SessionMode = Literal["live", "mock", "replay"]
# How the research loop spends its experiment budget.
ResearchStrategy = Literal["blackbox_tuning", "model_search"]

ALLOWED_MODEL_FAMILIES = (
    "logistic_regression",
    "random_forest",
    "hist_gradient_boosting",
    "xgboost",  # teaching alias → HistGradientBoosting in harness
)


class CreateSessionRequest(BaseModel):
    dataset_id: str | None = None
    # If uploading via multipart, dataset_id is filled after dataset-service responds.
    task_type: str = "classification"
    target_column: str
    metric: str = "f1"
    target_score: float = 0.7
    experiment_budget: int = 10
    scenario: str | None = None  # mock A1: happy|revise_loop|repair|...
    mode: SessionMode = "live"
    # Legacy: if True and mode omitted path, treated as mock. Prefer `mode`.
    mock: bool = False
    recording: str | None = None  # replay: filename stem under mocks/recordings/
    # Live: if True, gateway attaches bundled churn_sample.csv. If False, client must
    # POST /sessions/{id}/datasets with a CSV before the run starts — unless
    # reuse_dataset_filename points at a file under the gateway datasets catalog.
    use_sample_dataset: bool = True
    reuse_dataset_filename: str | None = None
    # Optional project to attach this training session under.
    project_id: str | None = None
    dataset_filename: str | None = None
    # blackbox_tuning = fixed model, HP search only; model_search = free family choice.
    research_strategy: ResearchStrategy = "model_search"
    fixed_model_family: str | None = None
    # Wall-clock train+score budget per trial (default 2 minutes).
    per_trial_timeout_seconds: int = Field(default=120, ge=30, le=600)

    @model_validator(mode="after")
    def _strategy_rules(self) -> "CreateSessionRequest":
        if self.research_strategy == "blackbox_tuning":
            if not self.fixed_model_family:
                raise ValueError("fixed_model_family is required for blackbox_tuning")
            if self.fixed_model_family not in ALLOWED_MODEL_FAMILIES:
                raise ValueError(
                    f"fixed_model_family must be one of {ALLOWED_MODEL_FAMILIES}"
                )
        return self


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str = "created"
    mock: bool = False
    mode: SessionMode = "live"
    replay: bool = False
    project_id: str | None = None


class SessionCommandResponse(BaseModel):
    session_id: str
    status: str
    message: str = ""
    mock: bool = False
    mode: SessionMode = "live"
