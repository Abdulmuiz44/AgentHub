from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class SkillRuntimeType(str, Enum):
    NATIVE_PYTHON = "native_python"
    MCP_STDIO = "mcp_stdio"
    MCP_HTTP = "mcp_http"
    SUBPROCESS_TOOL = "subprocess_tool"


class SkillTestStatus(str, Enum):
    UNKNOWN = "unknown"
    PASSED = "passed"
    FAILED = "failed"


class SkillCapability(BaseModel):
    operation: str
    read_only: bool = True
    description: str | None = None


class MCPStdioConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env_var_refs: list[str] = Field(default_factory=list)
    working_directory: str | None = None
    startup_timeout_seconds: float = Field(default=5.0, ge=0.5, le=30.0)
    call_timeout_seconds: float = Field(default=10.0, ge=0.5, le=120.0)
    tool_name: str | None = None
    test_input: dict[str, Any] = Field(default_factory=dict)


class SkillManifest(BaseModel):
    name: str
    version: str = "0.1.0"
    description: str
    runtime_type: SkillRuntimeType = SkillRuntimeType.NATIVE_PYTHON
    entrypoint: str | None = None
    scopes: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    enabled_by_default: bool = True
    input_schema_summary: dict[str, Any] = Field(default_factory=dict)
    output_schema_summary: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[SkillCapability] = Field(default_factory=list)
    mcp_stdio: MCPStdioConfig | None = None
    install_source: str | None = None
    test_input: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Skill name is required")
        return normalized

    @model_validator(mode="after")
    def validate_runtime_config(self) -> "SkillManifest":
        if self.runtime_type == SkillRuntimeType.MCP_STDIO and self.mcp_stdio is None:
            raise ValueError("mcp_stdio configuration is required for mcp_stdio skills")
        return self


class SkillRequest(BaseModel):
    operation: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = None


class SkillResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None
    runtime_type: SkillRuntimeType
    skill_name: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillTestResult(BaseModel):
    status: SkillTestStatus
    summary: str
    checked_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Skill(ABC):
    manifest: SkillManifest

    @abstractmethod
    def execute(self, request: SkillRequest) -> SkillResult: ...

    def test(self) -> SkillTestResult:
        return SkillTestResult(status=SkillTestStatus.PASSED, summary=f"{self.manifest.name} is available")
