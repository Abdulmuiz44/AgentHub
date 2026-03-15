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


class Skill(ABC):
    manifest: SkillManifest

    @abstractmethod
    def execute(self, payload: dict[str, Any]) -> dict[str, Any]: ...
