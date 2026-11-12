"""Harness tool request/response shells — the only interface agents get."""

from typing import Any

from pydantic import BaseModel, Field


class InspectDataRequest(BaseModel):
    session_id: str
    dataset_id: str
    correlation_id: str
    idempotency_key: str | None = None


class InspectDataResponse(BaseModel):
    dataset_id: str
    profile_view: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False


class ValidateExperimentRequest(BaseModel):
    session_id: str
    experiment_spec: dict[str, Any]
    correlation_id: str
    idempotency_key: str | None = None


class ValidateExperimentResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    mock: bool = False


class RunExperimentRequest(BaseModel):
    session_id: str
    experiment_spec: dict[str, Any]
    correlation_id: str
    idempotency_key: str  # required: retries must not repeat a trial


class RunExperimentResponse(BaseModel):
    experiment_id: str
    status: str
    train_metrics: dict[str, float] = Field(default_factory=dict)
    validation_metrics: dict[str, float] = Field(default_factory=dict)
    duration_seconds: float = 0.0
    artifact_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    mock: bool = False


class CompareExperimentsRequest(BaseModel):
    session_id: str
    experiment_ids: list[str]
    correlation_id: str


class CompareExperimentsResponse(BaseModel):
    comparison: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False


class GetHistoryRequest(BaseModel):
    session_id: str
    correlation_id: str
    limit: int = 50


class GetHistoryResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    mock: bool = False


class SaveArtifactRequest(BaseModel):
    session_id: str
    artifact_type: str
    name: str
    correlation_id: str
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SaveArtifactResponse(BaseModel):
    artifact_id: str
    mock: bool = False


class GenerateReportRequest(BaseModel):
    session_id: str
    correlation_id: str
    idempotency_key: str


class GenerateReportResponse(BaseModel):
    report_id: str
    local_path: str | None = None
    wandb_url: str | None = None
    mock: bool = False
