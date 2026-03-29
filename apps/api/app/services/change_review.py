from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import difflib
import hashlib
from pathlib import Path
from typing import Any

from sqlmodel import Session as DBSession

from app.config import settings
from memory import changes as change_repo
from memory.models import ChangeFile, ChangeSet

MAX_PREVIEW_CHARS = 500
MAX_DIFF_CHARS = 4000


class ChangeReviewError(RuntimeError):
    pass


@dataclass
class ProposedChangeRecord:
    path: str
    operation: str
    before_checksum: str | None
    after_checksum: str
    before_preview: str | None
    after_preview: str
    diff_preview: str
    proposed_content: str


class ChangeReviewService:
    def __init__(self, workspace_root: str | None = None) -> None:
        self.workspace_root = Path(workspace_root or settings.workspace_root).resolve()

    def summarize_change_sets(self, db: DBSession, run_id: int) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for change_set in change_repo.list_change_sets_for_run(db, run_id):
            files = [self.serialize_change_file(item) for item in change_repo.list_change_files(db, change_set.id)]
            payload.append(self.serialize_change_set(change_set, files))
        return payload

    def capture_proposed_changes(self, db: DBSession, run_id: int, step_id: str, skill_name: str, raw_changes: list[dict[str, Any]]) -> dict[str, Any]:
        normalized = [self._normalize_change(item) for item in raw_changes]
        change_set = change_repo.get_pending_change_set_for_run(db, run_id)
        if change_set is None:
            change_set = change_repo.create_change_set(db, run_id=run_id, status="pending", summary=f"Pending review for changes proposed by {skill_name}")

        existing_files = change_repo.list_change_files(db, change_set.id)
        for item in normalized:
            change_repo.add_change_file(
                db,
                change_set_id=change_set.id,
                path=item.path,
                operation=item.operation,
                before_checksum=item.before_checksum,
                after_checksum=item.after_checksum,
                before_preview=item.before_preview,
                after_preview=item.after_preview,
                diff_preview=item.diff_preview,
                proposed_content=item.proposed_content,
            )
        all_files = existing_files + change_repo.list_change_files(db, change_set.id)[len(existing_files):]
        summary = f"Pending review for {len(all_files)} file change(s)"
        change_set = change_repo.update_change_set(db, change_set, change_count=len(all_files), summary=summary)
        return {
            "change_set_id": change_set.id,
            "review_required": True,
            "pending_change_count": change_set.change_count,
            "files": [item.path for item in change_repo.list_change_files(db, change_set.id)],
            "step_id": step_id,
        }

    def apply_change_set(self, db: DBSession, change_set: ChangeSet) -> dict[str, Any]:
        change_files = change_repo.list_change_files(db, change_set.id)
        if not change_files:
            raise ChangeReviewError("No proposed changes are available to apply")

        targets = [(item, self._resolve_workspace_path(item.path)) for item in change_files]
        for item, target in targets:
            before_text = self._read_text_if_exists(target)
            current_checksum = self._checksum(before_text) if before_text is not None else None
            if current_checksum != item.before_checksum:
                raise ChangeReviewError(f"Workspace file is stale for {item.path}")

        for item, target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(item.proposed_content, encoding="utf-8")

        summary = f"Applied {len(targets)} file change(s)"
        change_repo.update_change_set(db, change_set, status="applied", apply_summary=summary, failure_summary=None, applied_at=datetime.utcnow())
        return {"summary": summary, "files": [item.path for item, _target in targets]}

    def reject_change_set(self, db: DBSession, change_set: ChangeSet) -> dict[str, Any]:
        files = change_repo.list_change_files(db, change_set.id)
        summary = f"Rejected {len(files)} file change(s)"
        change_repo.update_change_set(db, change_set, status="rejected", reject_summary=summary, failure_summary=None, rejected_at=datetime.utcnow())
        return {"summary": summary, "files": [item.path for item in files]}

    def get_pending_change_set(self, db: DBSession, run_id: int) -> ChangeSet | None:
        return change_repo.get_pending_change_set_for_run(db, run_id)

    def mark_apply_failed(self, db: DBSession, change_set: ChangeSet, summary: str) -> ChangeSet:
        return change_repo.update_change_set(db, change_set, failure_summary=summary)

    def serialize_change_set(self, change_set: ChangeSet, files: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": change_set.id,
            "run_id": change_set.run_id,
            "status": change_set.status,
            "change_count": change_set.change_count,
            "summary": change_set.summary,
            "apply_summary": change_set.apply_summary,
            "reject_summary": change_set.reject_summary,
            "failure_summary": change_set.failure_summary,
            "created_at": change_set.created_at,
            "updated_at": change_set.updated_at,
            "files": files,
        }

    @staticmethod
    def serialize_change_file(change_file: ChangeFile) -> dict[str, Any]:
        return {
            "id": change_file.id,
            "path": change_file.path,
            "operation": change_file.operation,
            "before_checksum": change_file.before_checksum,
            "after_checksum": change_file.after_checksum,
            "before_preview": change_file.before_preview,
            "after_preview": change_file.after_preview,
            "diff_preview": change_file.diff_preview,
            "created_at": change_file.created_at,
            "updated_at": change_file.updated_at,
        }

    def _normalize_change(self, raw_change: dict[str, Any]) -> ProposedChangeRecord:
        path = str(raw_change.get("path", "")).strip()
        operation = str(raw_change.get("operation", "")).strip() or "overwrite"
        content = raw_change.get("content")
        if not path:
            raise ChangeReviewError("Proposed change is missing a path")
        if operation not in {"create", "overwrite", "append"}:
            raise ChangeReviewError(f"Unsupported proposed change operation for {path}")
        if not isinstance(content, str):
            raise ChangeReviewError(f"Proposed change content must be UTF-8 text for {path}")

        target = self._resolve_workspace_path(path)
        before_text = self._read_text_if_exists(target)
        if operation == "append" and before_text is not None:
            proposed_content = before_text + content
        else:
            proposed_content = content
        before_checksum = self._checksum(before_text) if before_text is not None else None
        after_checksum = self._checksum(proposed_content)
        before_preview = self._preview(before_text) if before_text is not None else None
        after_preview = self._preview(proposed_content)
        diff_preview = self._build_diff(path, before_text, proposed_content)
        return ProposedChangeRecord(
            path=path,
            operation=operation,
            before_checksum=before_checksum,
            after_checksum=after_checksum,
            before_preview=before_preview,
            after_preview=after_preview,
            diff_preview=diff_preview,
            proposed_content=proposed_content,
        )

    def _resolve_workspace_path(self, relative_path: str) -> Path:
        candidate = (self.workspace_root / relative_path).resolve()
        if not str(candidate).startswith(str(self.workspace_root)):
            raise ChangeReviewError("Proposed path escapes workspace root")
        return candidate

    @staticmethod
    def _checksum(value: str | None) -> str | None:
        if value is None:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _preview(value: str | None) -> str | None:
        if value is None:
            return None
        return value[:MAX_PREVIEW_CHARS]

    def _read_text_if_exists(self, path: Path) -> str | None:
        if not path.exists():
            return None
        if not path.is_file():
            raise ChangeReviewError(f"Target path is not a file: {path}")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ChangeReviewError(f"Only UTF-8 text files are supported: {path}") from exc

    @staticmethod
    def _build_diff(path: str, before_text: str | None, after_text: str) -> str:
        before_lines = [] if before_text is None else before_text.splitlines(keepends=True)
        after_lines = after_text.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        return diff[:MAX_DIFF_CHARS]
