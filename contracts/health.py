from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str | None = None
    mock: bool = False
    details: dict = Field(default_factory=dict)
