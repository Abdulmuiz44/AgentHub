from pathlib import Path

from .base import Skill, SkillManifest
from .fetch import FetchSkill
from .filesystem import FilesystemConfig, FilesystemSkill


class SkillRegistry:
    def __init__(self, skills: dict[str, Skill] | None = None) -> None:
        self._skills = skills or {}

    def list_manifests(self) -> list[SkillManifest]:
        return [skill.manifest for skill in self._skills.values()]

    def get_skill(self, skill_name: str) -> Skill | None:
        return self._skills.get(skill_name)

    @classmethod
    def default(cls, workspace_root: str | Path = ".") -> "SkillRegistry":
        fs_skill = FilesystemSkill(FilesystemConfig(workspace_root=workspace_root))
        fetch_skill = FetchSkill()
        return cls({"filesystem": fs_skill, "fetch": fetch_skill})
