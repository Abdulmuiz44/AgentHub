from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class SkillCapability(BaseModel):
    operation: str
    read_only: bool = True


class SkillManifest(BaseModel):
    name: str
    version: str
    description: str
    entrypoint: str | None = None
    permissions: list[str] = Field(default_factory=list)
    capabilities: list[SkillCapability] = Field(default_factory=list)


class SkillRequest(BaseModel):
    operation: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class SkillResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    error: str | None = None


class Skill(ABC):
    manifest: SkillManifest

    @abstractmethod
    def execute(self, request: SkillRequest) -> SkillResult: ...
