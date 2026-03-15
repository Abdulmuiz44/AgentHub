from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EventType(str, Enum):
    RUN_STARTED = "run.started"
    PLAN_CREATED = "plan.created"
    TOOL_CALLED = "tool.called"
    TOOL_COMPLETED = "tool.completed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"


class AgentRequest(BaseModel):
    task: str
    session_id: int | None = None
    provider: str
    model: str
    enabled_skills: list[str] = Field(default_factory=list)


class RunContext(BaseModel):
    run_id: int
    session_id: int | None = None
    requested_at: datetime = Field(default_factory=datetime.utcnow)


class PlanStep(BaseModel):
    id: str
    title: str
    status: RunStatus = RunStatus.QUEUED


class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class TraceEvent(BaseModel):
    run_id: int
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)
