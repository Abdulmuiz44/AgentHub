from datetime import datetime

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
    status: str = "pending"
    final_output: str | None = None
    synthesis_mode: str | None = None
    synthesis_status: str | None = None
    synthesis_error_summary: str | None = None
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
    reason: str
    status: str = "pending"


class SkillDefinition(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    version: str = "0.1.0"
    enabled: bool = True


class ProviderConfig(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider_name: str
    base_url: str | None = None
    api_key_ref: str | None = None
