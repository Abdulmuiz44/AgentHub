from pathlib import Path

from .base import SkillManifest
from .filesystem import FilesystemConfig, FilesystemSkill


class SkillRegistry:
    def __init__(self, manifests: list[SkillManifest] | None = None) -> None:
        self._manifests = manifests or []

    def list_manifests(self) -> list[SkillManifest]:
        return self._manifests

    @classmethod
    def default(cls, workspace_root: str | Path = "."):
        fs_skill = FilesystemSkill(FilesystemConfig(workspace_root=workspace_root))
        return cls([fs_skill.manifest])
