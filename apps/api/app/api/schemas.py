from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    name: str | None = None


class SessionResponse(BaseModel):
    id: int
    name: str | None = None
    created_at: datetime


class RunCreateRequest(BaseModel):
    task: str = Field(min_length=1)
    provider: str = "builtin"
    model: str = "deterministic"
    session_id: int | None = None
    enabled_skills: list[str] = Field(default_factory=list)
    execute_now: bool = True


class TraceResponse(BaseModel):
    id: int
    run_id: int
    event_type: str
    payload: str
    created_at: datetime


class RunResponse(BaseModel):
    id: int
    session_id: int
    task: str
    provider: str
    model: str
    status: str
    final_output: str | None = None
    synthesis_mode: str | None = None
    synthesis_status: str | None = None
    synthesis_error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class RunCreateResponse(BaseModel):
    run: RunResponse
    trace_events: list[TraceResponse]


class RunExecutionSummary(BaseModel):
    run_id: int
    status: str
    output: str
    plan: list[dict[str, Any]] = Field(default_factory=list)
    step_results: list[dict[str, Any]] = Field(default_factory=list)


class ProviderMetadata(BaseModel):
    name: str
    display_name: str
    models: list[str] = Field(default_factory=list)
    supports_streaming: bool = False


class ProviderSummaryResponse(BaseModel):
    provider: ProviderMetadata
    configuration_status: str
    is_configured: bool


class ProviderModelsItemResponse(BaseModel):
    provider_name: str
    display_name: str
    configuration_status: str
    is_configured: bool
    models: list[str] = Field(default_factory=list)


class ProviderModelsResponse(BaseModel):
    providers: list[ProviderModelsItemResponse] = Field(default_factory=list)


class ProviderHealthCheckRequest(BaseModel):
    provider: str = Field(min_length=1)


class ProviderHealthCheckResponse(BaseModel):
    provider: str
    configuration_status: str
    healthy: bool
    message: str
