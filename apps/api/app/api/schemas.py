from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    name: str | None = None


class SessionResponse(BaseModel):
    id: int
    name: str | None = None
    created_at: datetime


class RunCreateRequest(BaseModel):
    task: str = Field(min_length=1)
    provider: str
    model: str
    session_id: int | None = None
    enabled_skills: list[str] = Field(default_factory=list)


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
    created_at: datetime


class RunCreateResponse(BaseModel):
    run: RunResponse
    trace_events: list[TraceResponse]
