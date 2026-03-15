from __future__ import annotations

from pathlib import Path

from .base import Skill, SkillCapability, SkillManifest


class FilesystemConfig:
    def __init__(self, workspace_root: str | Path, max_file_size_bytes: int = 1024 * 1024) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.max_file_size_bytes = max_file_size_bytes


class FilesystemValidationError(ValueError):
    pass


class FilesystemSkill(Skill):
    manifest = SkillManifest(
        name="filesystem",
        version="0.1.0",
        description="Read-only filesystem access scoped to workspace root",
        permissions=["fs:read"],
        capabilities=[
            SkillCapability(operation="list_directory", read_only=True),
            SkillCapability(operation="read_text_file", read_only=True),
        ],
    )

    def __init__(self, config: FilesystemConfig) -> None:
        self.config = config

    def _resolve_path(self, relative_path: str) -> Path:
        candidate = (self.config.workspace_root / relative_path).resolve()
        if not str(candidate).startswith(str(self.config.workspace_root)):
            raise FilesystemValidationError("Path escapes workspace root")
        return candidate

    def list_directory(self, relative_path: str = ".") -> list[str]:
        directory = self._resolve_path(relative_path)
        if not directory.is_dir():
            raise FilesystemValidationError("Path is not a directory")
        return sorted(item.name for item in directory.iterdir())

    def read_text_file(self, relative_path: str) -> str:
        target = self._resolve_path(relative_path)
        if not target.is_file():
            raise FilesystemValidationError("Path is not a file")
        if target.stat().st_size > self.config.max_file_size_bytes:
            raise FilesystemValidationError("File exceeds max allowed size")

        raw = target.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FilesystemValidationError("Only UTF-8 text files are supported") from exc

    def execute(self, payload: dict[str, str]) -> dict[str, object]:
        operation = payload.get("operation")
        path = payload.get("path", ".")
        if operation == "list_directory":
            return {"entries": self.list_directory(path)}
        if operation == "read_text_file":
            return {"content": self.read_text_file(path)}
        raise FilesystemValidationError(f"Unsupported operation: {operation}")


def load_manifests(_path: str) -> list[SkillManifest]:
    return [FilesystemSkill.manifest]
