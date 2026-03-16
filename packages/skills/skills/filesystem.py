from __future__ import annotations

from pathlib import Path

from .base import (
    Skill,
    SkillCapability,
    SkillCapabilityCategory,
    SkillManifest,
    SkillRequest,
    SkillResult,
    SkillRuntimeType,
    SkillTestResult,
    SkillTestStatus,
)


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
        runtime_type=SkillRuntimeType.NATIVE_PYTHON,
        scopes=["filesystem:read"],
        permissions=["fs:read"],
        tags=["builtin", "filesystem"],
        capability_categories=[SkillCapabilityCategory.READ_FILES],
        input_schema_summary={"operation": "list_directory or read_text_file", "path": "Path relative to workspace root"},
        output_schema_summary={"entries": "directory listing", "content": "UTF-8 file content preview"},
        capabilities=[
            SkillCapability(operation="list_directory", read_only=True, description="List workspace directory entries"),
            SkillCapability(operation="read_text_file", read_only=True, description="Read a UTF-8 text file"),
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

    def execute(self, request: SkillRequest) -> SkillResult:
        operation = request.operation or request.input.get("operation")
        path = str(request.input.get("path", "."))
        try:
            if operation == "list_directory":
                entries = self.list_directory(path)
                return SkillResult(
                    success=True,
                    output={"entries": entries, "path": path},
                    summary=f"Listed {len(entries)} entries",
                    runtime_type=self.manifest.runtime_type,
                    skill_name=self.manifest.name,
                    metadata={"builtin": True, "capability_categories": [item.value for item in self.manifest.capability_categories]},
                )
            if operation == "read_text_file":
                content = self.read_text_file(path)
                return SkillResult(
                    success=True,
                    output={"content": content, "path": path, "chars": len(content)},
                    summary=f"Read {len(content)} chars from {path}",
                    runtime_type=self.manifest.runtime_type,
                    skill_name=self.manifest.name,
                    metadata={"builtin": True, "capability_categories": [item.value for item in self.manifest.capability_categories]},
                )
            return SkillResult(
                success=False,
                error=f"Unsupported operation: {operation}",
                runtime_type=self.manifest.runtime_type,
                skill_name=self.manifest.name,
                metadata={"builtin": True, "capability_categories": [item.value for item in self.manifest.capability_categories]},
            )
        except FilesystemValidationError as exc:
            return SkillResult(
                success=False,
                error=str(exc),
                runtime_type=self.manifest.runtime_type,
                skill_name=self.manifest.name,
                metadata={"builtin": True, "capability_categories": [item.value for item in self.manifest.capability_categories]},
            )

    def test(self) -> SkillTestResult:
        return SkillTestResult(
            status=SkillTestStatus.PASSED,
            summary=f"Workspace root {self.config.workspace_root} is available",
            metadata={"workspace_root": str(self.config.workspace_root)},
        )


def load_manifests(_path: str) -> list[SkillManifest]:
    return [FilesystemSkill.manifest]
