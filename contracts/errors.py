"""Typed service errors — callers must never hang on a dead dependency."""

from pydantic import BaseModel, Field


class ServiceError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    correlation_id: str | None = None
    details: dict = Field(default_factory=dict)
