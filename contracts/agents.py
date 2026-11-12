"""Typed agent-service invoke contracts."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class LeadName(str, Enum):
    DATA_SCIENTIST = "data_scientist"
    HYPOTHESIS_GENERATOR = "hypothesis_generator"
    ML_ENGINEER = "ml_engineer"
    JUDGE = "judge"


class SubagentName(str, Enum):
    DATA_PROFILER = "data_profiler"
    LEAKAGE_AUDITOR = "leakage_auditor"
    FEATURE_ANALYST = "feature_analyst"
    MEMORY_RETRIEVER = "memory_retriever"
    HYPOTHESIS_DRAFTER = "hypothesis_drafter"
    NOVELTY_CHECKER = "novelty_checker"
    CONFIG_VALIDATOR = "config_validator"
    EXPERIMENT_RUNNER = "experiment_runner"
    ERROR_REPAIR = "error_repair"
    METRIC_ANALYST = "metric_analyst"
    OVERFITTING_CHECKER = "overfitting_checker"
    INDEPENDENT_REVIEWER = "independent_reviewer"


class AgentInvokeRequest(BaseModel):
    session_id: str
    correlation_id: str
    lead: LeadName
    subagent: SubagentName
    input: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False


class AgentInvokeResponse(BaseModel):
    session_id: str
    lead: LeadName
    subagent: SubagentName
    output: dict[str, Any] = Field(default_factory=dict)
    mock: bool = False
