from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    PLAN_CREATED = "plan.created"
    TOOL_REQUESTED = "tool.requested"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    SYNTHESIS_STARTED = "synthesis.started"
    SYNTHESIS_COMPLETED = "synthesis.completed"
    SYNTHESIS_FAILED = "synthesis.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class AgentRequest(BaseModel):
    task: str
    session_id: int | None = None
    provider: str = "builtin"
    model: str = "deterministic"
    enabled_skills: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)


class RunContext(BaseModel):
    run_id: int
    session_id: int | None = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStep(BaseModel):
    id: str
    title: str
    skill_name: str | None = None
    skill_input: dict[str, Any] = Field(default_factory=dict)
    selection_reason: str | None = None


class EvidenceItem(BaseModel):
    source_type: str
    source_ref: str
    title: str | None = None
    excerpt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class StepExecutionResult(BaseModel):
    step_id: str
    success: bool
    summary: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SynthesisMetadata(BaseModel):
    mode: str
    status: str
    provider: str | None = None
    model: str | None = None
    provider_status: str | None = None
    provider_usage_summary: str | None = None
    error_summary: str | None = None


class RunExecutionResult(BaseModel):
    status: RunStatus
    output: str
    plan: list[PlanStep] = Field(default_factory=list)
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceBundle = Field(default_factory=EvidenceBundle)
    synthesis: SynthesisMetadata | None = None


class TraceEvent(BaseModel):
    run_id: int
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
