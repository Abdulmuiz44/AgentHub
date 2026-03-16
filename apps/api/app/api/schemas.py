from datetime import datetime
from typing import Any, Literal

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
    execute_now: bool = False
    execution_mode: Literal["deterministic", "model_assisted"] = "deterministic"


class ApprovalResponse(BaseModel):
    id: int
    run_id: int
    step_id: str | None = None
    reason: str
    status: str
    resolution_summary: str | None = None
    created_at: datetime
    updated_at: datetime


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
    execution_mode: str
    planning_source: str
    planning_summary: str
    fallback_reason: str | None = None
    status: str
    cancel_requested: bool = False
    final_output: str | None = None
    synthesis_mode: str | None = None
    synthesis_status: str | None = None
    synthesis_error_summary: str | None = None
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    budget_config: dict[str, Any] = Field(default_factory=dict)
    budget_usage_summary: dict[str, Any] = Field(default_factory=dict)
    pending_approval: ApprovalResponse | None = None
    created_at: datetime
    updated_at: datetime


class RunCreateResponse(BaseModel):
    run: RunResponse
    trace_events: list[TraceResponse]


class ApprovalResolveResponse(BaseModel):
    run: RunResponse
    approval: ApprovalResponse


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
    message: str | None = None


class ProviderModelsResponse(BaseModel):
    providers: list[ProviderModelsItemResponse] = Field(default_factory=list)


class ProviderHealthCheckRequest(BaseModel):
    provider: str = Field(min_length=1)


class ProviderHealthCheckResponse(BaseModel):
    provider: str
    configuration_status: str
    healthy: bool
    message: str


class SkillManifestPayload(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str
    runtime_type: str
    scopes: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    capability_categories: list[str] = Field(default_factory=list)
    enabled_by_default: bool = True
    input_schema_summary: dict[str, Any] = Field(default_factory=dict)
    output_schema_summary: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[dict[str, Any]] = Field(default_factory=list)
    config_fields: list[dict[str, Any]] = Field(default_factory=list)
    mcp_stdio: dict[str, Any] | None = None
    install_source: str | None = None
    test_input: dict[str, Any] = Field(default_factory=dict)


class SkillConfigFieldResponse(BaseModel):
    key: str
    label: str | None = None
    description: str | None = None
    required: bool = False
    secret: bool = False
    value_type: str
    default: Any | None = None
    env_var_allowed: bool = False
    example: str | None = None


class SkillConfigValueResponse(BaseModel):
    key: str
    value: Any | None = None
    configured: bool
    secret_binding: str | None = None
    uses_environment_binding: bool = False


class SkillConfigStateResponse(BaseModel):
    readiness_status: str
    readiness_summary: str
    values: list[SkillConfigValueResponse] = Field(default_factory=list)


class SkillConfigResponse(BaseModel):
    skill_name: str
    config_schema: list[SkillConfigFieldResponse] = Field(default_factory=list)
    state: SkillConfigStateResponse
    updated_at: datetime | None = None


class SkillResponse(BaseModel):
    id: int | None = None
    name: str
    version: str
    description: str
    runtime_type: str
    enabled: bool
    is_builtin: bool
    scopes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    capability_categories: list[str] = Field(default_factory=list)
    install_source: str | None = None
    last_test_status: str | None = None
    last_test_summary: str | None = None
    last_tested_at: datetime | None = None
    readiness_status: str
    readiness_summary: str
    config_schema: list[SkillConfigFieldResponse] = Field(default_factory=list)
    config_state: SkillConfigStateResponse
    manifest: dict[str, Any] = Field(default_factory=dict)


class SkillInstallRequest(BaseModel):
    manifest: SkillManifestPayload | None = None
    manifest_path: str | None = None


class SkillConfigUpdateRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    secret_bindings: dict[str, str] = Field(default_factory=dict)


class SkillTestResponse(BaseModel):
    skill: SkillResponse
    status: str
    summary: str
    checked_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
