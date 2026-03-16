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


class SkillConfigValueType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    PATH = "path"


class SkillReadinessStatus(str, Enum):
    READY = "ready"
    MISSING_REQUIRED_CONFIG = "missing_required_config"
    MISSING_REQUIRED_ENV_BINDING = "missing_required_env_binding"
    INVALID_CONFIG = "invalid_config"


class SkillCapabilityCategory(str, Enum):
    READ_FILES = "read_files"
    WRITE_FILES = "write_files"
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"
    RENDERED_BROWSE = "rendered_browse"
    SHELL_VERIFY = "shell_verify"
    CUSTOM_TOOL = "custom_tool"


class SkillCapability(BaseModel):
    operation: str
    read_only: bool = True
    description: str | None = None


class SkillConfigField(BaseModel):
    key: str
    label: str | None = None
    description: str | None = None
    required: bool = False
    secret: bool = False
    value_type: SkillConfigValueType = SkillConfigValueType.STRING
    default: Any | None = None
    env_var_allowed: bool = False
    example: str | None = None

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Config field key is required")
        return normalized

    @model_validator(mode="after")
    def validate_secret_defaults(self) -> "SkillConfigField":
        if self.secret and self.default is not None:
            raise ValueError("Secret config fields cannot declare default values")
        if self.secret and not self.env_var_allowed:
            self.env_var_allowed = True
        return self


class MCPStdioConfig(BaseModel):
    command: str
    args: list[str] = Field(default_factory=list)
    env_var_refs: list[str] = Field(default_factory=list)
    env_map: dict[str, str] = Field(default_factory=dict)
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
    capability_categories: list[SkillCapabilityCategory] = Field(default_factory=list)
    enabled_by_default: bool = True
    input_schema_summary: dict[str, Any] = Field(default_factory=dict)
    output_schema_summary: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[SkillCapability] = Field(default_factory=list)
    config_fields: list[SkillConfigField] = Field(default_factory=list)
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


class UnavailableSkill(Skill):
    def __init__(
        self,
        manifest: SkillManifest,
        *,
        summary: str,
        readiness_status: SkillReadinessStatus,
        is_builtin: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.manifest = manifest
        self.summary = summary
        self.readiness_status = readiness_status
        self.is_builtin = is_builtin
        self.metadata = metadata or {}

    def execute(self, request: SkillRequest) -> SkillResult:
        return SkillResult(
            success=False,
            error=self.summary,
            summary=self.summary,
            runtime_type=self.manifest.runtime_type,
            skill_name=self.manifest.name,
            metadata={
                "builtin": self.is_builtin,
                "config_readiness": self.readiness_status.value,
                **self.metadata,
            },
        )

    def test(self) -> SkillTestResult:
        return SkillTestResult(
            status=SkillTestStatus.FAILED,
            summary=self.summary,
            metadata={
                "builtin": self.is_builtin,
                "config_readiness": self.readiness_status.value,
                **self.metadata,
            },
        )
