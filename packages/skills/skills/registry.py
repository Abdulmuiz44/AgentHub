from __future__ import annotations

from pathlib import Path
from typing import Callable

from .base import Skill, SkillManifest, SkillRuntimeType
from .fetch import FetchSkill
from .filesystem import FilesystemConfig, FilesystemSkill
from .mcp_stdio import MCPStdioSkill
from .search_provider import SearchProviderResolver, SearchProviderResolverConfig
from .web_search import WebSearchSkill


NativeSkillFactory = Callable[[], Skill]


class SkillRegistry:
    def __init__(self, skills: dict[str, Skill] | None = None) -> None:
        self._skills = skills or {}

    def list_manifests(self) -> list[SkillManifest]:
        return [skill.manifest for skill in self._skills.values()]

    def get_skill(self, skill_name: str) -> Skill | None:
        return self._skills.get(skill_name)

    @classmethod
    def from_manifests(
        cls,
        manifests: list[SkillManifest],
        *,
        workspace_root: str | Path = ".",
        search_provider: str | None = None,
        searxng_base_url: str | None = None,
    ) -> "SkillRegistry":
        skills: dict[str, Skill] = {}
        native_factories = builtin_skill_factories(
            workspace_root=workspace_root,
            search_provider=search_provider,
            searxng_base_url=searxng_base_url,
        )
        for manifest in manifests:
            if manifest.runtime_type == SkillRuntimeType.NATIVE_PYTHON:
                factory = native_factories.get(manifest.name)
                if factory is not None:
                    skills[manifest.name] = factory()
            elif manifest.runtime_type == SkillRuntimeType.MCP_STDIO:
                skills[manifest.name] = MCPStdioSkill(manifest)
        return cls(skills)

    @classmethod
    def default(
        cls,
        workspace_root: str | Path = ".",
        *,
        search_provider: str | None = None,
        searxng_base_url: str | None = None,
    ) -> "SkillRegistry":
        factories = builtin_skill_factories(
            workspace_root=workspace_root,
            search_provider=search_provider,
            searxng_base_url=searxng_base_url,
        )
        return cls({name: factory() for name, factory in factories.items()})


def builtin_skill_factories(
    *,
    workspace_root: str | Path = ".",
    search_provider: str | None = None,
    searxng_base_url: str | None = None,
) -> dict[str, NativeSkillFactory]:
    workspace_root = Path(workspace_root)
    return {
        "filesystem": lambda: FilesystemSkill(FilesystemConfig(workspace_root=workspace_root)),
        "fetch": lambda: FetchSkill(),
        "web_search": lambda: WebSearchSkill(
            resolver=SearchProviderResolver(
                SearchProviderResolverConfig(explicit_provider=search_provider, searxng_base_url=searxng_base_url)
            )
        ),
    }


def builtin_manifests() -> list[SkillManifest]:
    return [FilesystemSkill.manifest, FetchSkill.manifest, WebSearchSkill.manifest]
