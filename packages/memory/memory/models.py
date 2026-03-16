from datetime import datetime
from typing import Any

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="session.id")
    task: str
    provider: str
    model: str
    execution_mode: str = "deterministic"
    planning_source: str = "deterministic"
    planning_summary: str = ""
    fallback_reason: str | None = None
    status: str = "pending"
    cancel_requested: bool = False
    final_output: str | None = None
    synthesis_mode: str | None = None
    synthesis_status: str | None = None
    synthesis_error_summary: str | None = None
    execution_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    evidence_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    budget_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    budget_usage_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    execution_state: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TraceEventRecord(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id")
    event_type: str
    payload: str = "{}"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRequest(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id")
    step_id: str | None = None
    reason: str
    status: str = "pending"
    resolution_summary: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SkillDefinition(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    version: str = "0.1.0"
    description: str = ""
    runtime_type: str = "native_python"
    enabled: bool = True
    is_builtin: bool = False
    scopes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    manifest_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    config_values_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    secret_bindings_json: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    readiness_status: str = "ready"
    readiness_summary: str = "Ready"
    install_source: str | None = None
    last_test_status: str | None = None
    last_test_summary: str | None = None
    last_tested_at: datetime | None = None
    config_updated_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProviderConfig(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider_name: str
    base_url: str | None = None
    api_key_ref: str | None = None
