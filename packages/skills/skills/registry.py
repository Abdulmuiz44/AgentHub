from pathlib import Path

from .base import Skill, SkillManifest
from .fetch import FetchSkill
from .filesystem import FilesystemConfig, FilesystemSkill
from .search_provider import SearchProviderResolver, SearchProviderResolverConfig
from .web_search import WebSearchSkill


class SkillRegistry:
    def __init__(self, skills: dict[str, Skill] | None = None) -> None:
        self._skills = skills or {}

    def list_manifests(self) -> list[SkillManifest]:
        return [skill.manifest for skill in self._skills.values()]

    def get_skill(self, skill_name: str) -> Skill | None:
        return self._skills.get(skill_name)

    @classmethod
    def default(
        cls,
        workspace_root: str | Path = ".",
        *,
        search_provider: str | None = None,
        searxng_base_url: str | None = None,
    ) -> "SkillRegistry":
        fs_skill = FilesystemSkill(FilesystemConfig(workspace_root=workspace_root))
        fetch_skill = FetchSkill()
        web_search_skill = WebSearchSkill(
            resolver=SearchProviderResolver(
                SearchProviderResolverConfig(
                    explicit_provider=search_provider,
                    searxng_base_url=searxng_base_url,
                )
            )
        )
        return cls({"filesystem": fs_skill, "fetch": fetch_skill, "web_search": web_search_skill})
