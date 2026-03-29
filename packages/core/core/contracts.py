from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ExecutionMode(str, Enum):
    DETERMINISTIC = "deterministic"
    MODEL_ASSISTED = "model_assisted"


class MutationApplyMode(str, Enum):
    DIRECT_APPLY = "direct_apply"
    REVIEW_FIRST = "review_first"


class ReviewStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"


class PlanningSource(str, Enum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"
    FALLBACK = "fallback"


class EventType(str, Enum):
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    RUN_PAUSED = "run.paused"
    RUN_RESUMED = "run.resumed"
    RUN_CANCEL_REQUESTED = "run.cancel_requested"
    RUN_CANCELLED = "run.cancelled"
    PLANNING_STARTED = "planning.started"
    PLAN_CREATED = "planning.completed"
    PLANNING_FALLBACK = "planning.fallback"
    PLAN_VALIDATION_FAILED = "plan.validation_failed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_RESOLVED = "approval.resolved"
    BUDGET_ENFORCED = "budget.enforced"
    TOOL_REQUESTED = "tool.requested"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"
    CHANGE_PROPOSED = "change.proposed"
    CHANGE_REVIEW_PENDING = "change.review_pending"
    CHANGE_APPLY_REQUESTED = "change.apply_requested"
    CHANGE_APPLIED = "change.applied"
    CHANGE_APPLY_FAILED = "change.apply_failed"
    CHANGE_REJECTED = "change.rejected"
    SYNTHESIS_STARTED = "synthesis.started"
    SYNTHESIS_COMPLETED = "synthesis.completed"
    SYNTHESIS_FAILED = "synthesis.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class ExecutionBudget(BaseModel):
    max_plan_steps: int = Field(default=3, ge=1, le=8)
    max_tool_invocations: int = Field(default=4, ge=1, le=12)
    max_tool_calls_per_skill: int = Field(default=2, ge=1, le=6)
    max_fetched_sources: int = Field(default=3, ge=1, le=8)
    max_browser_uses: int = Field(default=1, ge=0, le=4)
    max_shell_uses: int = Field(default=1, ge=0, le=4)


class PlanningSkillDescriptor(BaseModel):
    name: str
    runtime_type: str
    description: str
    scopes: list[str] = Field(default_factory=list)
    capability_categories: list[str] = Field(default_factory=list)
    readiness: str
    approval_required: bool = False
    is_builtin: bool = False


class AgentRequest(BaseModel):
    task: str
    session_id: int | None = None
    provider: str = "builtin"
    model: str = "deterministic"
    enabled_skills: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    planning_skills: list[PlanningSkillDescriptor] = Field(default_factory=list)
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    mutation_apply_mode: MutationApplyMode = MutationApplyMode.DIRECT_APPLY
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)


class RunContext(BaseModel):
    run_id: int
    session_id: int | None = None
    workspace_root: str | None = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStep(BaseModel):
    id: str
    title: str
    skill_name: str | None = None
    skill_input: dict[str, Any] = Field(default_factory=dict)
    selection_reason: str | None = None
    decision_summary: str | None = None
    requires_approval: bool = False
    approval_reason: str | None = None


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


class ExecutionState(BaseModel):
    enabled_skills: list[str] = Field(default_factory=list)
    budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
    plan: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    evidence: EvidenceBundle = Field(default_factory=EvidenceBundle)
    working_search_results: list[dict[str, Any]] = Field(default_factory=list)
    planning_source: PlanningSource = PlanningSource.DETERMINISTIC
    planning_summary: str = ""
    fallback_reason: str | None = None
    budget_usage_summary: dict[str, Any] = Field(default_factory=dict)
    pending_approval_id: int | None = None
    pending_change_set_id: int | None = None
    pending_change_count: int = 0
    review_status: ReviewStatus = ReviewStatus.NONE
    failure_context: str | None = None
    cancel_requested: bool = False


class RunExecutionResult(BaseModel):
    status: RunStatus
    output: str
    plan: list[PlanStep] = Field(default_factory=list)
    step_results: list[StepExecutionResult] = Field(default_factory=list)
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceBundle = Field(default_factory=EvidenceBundle)
    synthesis: SynthesisMetadata | None = None
    execution_mode: ExecutionMode = ExecutionMode.DETERMINISTIC
    planning_source: PlanningSource = PlanningSource.DETERMINISTIC
    planning_summary: str = ""
    fallback_reason: str | None = None
    budget_config: dict[str, Any] = Field(default_factory=dict)
    budget_usage_summary: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    run_id: int
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
