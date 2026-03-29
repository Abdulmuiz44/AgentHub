from datetime import datetime

from sqlmodel import Session as DBSession, select

from .models import ChangeFile, ChangeSet


def create_change_set(db: DBSession, *, run_id: int, status: str = "pending", summary: str = "") -> ChangeSet:
    change_set = ChangeSet(run_id=run_id, status=status, summary=summary)
    db.add(change_set)
    db.commit()
    db.refresh(change_set)
    return change_set


def add_change_file(
    db: DBSession,
    *,
    change_set_id: int,
    path: str,
    operation: str,
    before_checksum: str | None,
    after_checksum: str | None,
    before_preview: str | None,
    after_preview: str | None,
    diff_preview: str,
    proposed_content: str,
) -> ChangeFile:
    change_file = ChangeFile(
        change_set_id=change_set_id,
        path=path,
        operation=operation,
        before_checksum=before_checksum,
        after_checksum=after_checksum,
        before_preview=before_preview,
        after_preview=after_preview,
        diff_preview=diff_preview,
        proposed_content=proposed_content,
    )
    db.add(change_file)
    db.commit()
    db.refresh(change_file)
    return change_file


def get_change_set(db: DBSession, change_set_id: int) -> ChangeSet | None:
    return db.get(ChangeSet, change_set_id)


def list_change_sets_for_run(db: DBSession, run_id: int) -> list[ChangeSet]:
    statement = select(ChangeSet).where(ChangeSet.run_id == run_id).order_by(ChangeSet.id)
    return db.exec(statement).all()


def get_pending_change_set_for_run(db: DBSession, run_id: int) -> ChangeSet | None:
    statement = (
        select(ChangeSet)
        .where(ChangeSet.run_id == run_id)
        .where(ChangeSet.status == "pending")
        .order_by(ChangeSet.id.desc())
    )
    return db.exec(statement).first()


def list_change_files(db: DBSession, change_set_id: int) -> list[ChangeFile]:
    statement = select(ChangeFile).where(ChangeFile.change_set_id == change_set_id).order_by(ChangeFile.id)
    return db.exec(statement).all()


def update_change_set(
    db: DBSession,
    change_set: ChangeSet,
    *,
    status: str | None = None,
    change_count: int | None = None,
    summary: str | None = None,
    apply_summary: str | None = None,
    reject_summary: str | None = None,
    failure_summary: str | None = None,
    applied_at: datetime | None = None,
    rejected_at: datetime | None = None,
) -> ChangeSet:
    if status is not None:
        change_set.status = status
    if change_count is not None:
        change_set.change_count = change_count
    if summary is not None:
        change_set.summary = summary
    if apply_summary is not None:
        change_set.apply_summary = apply_summary
    if reject_summary is not None:
        change_set.reject_summary = reject_summary
    if failure_summary is not None:
        change_set.failure_summary = failure_summary
    if applied_at is not None:
        change_set.applied_at = applied_at
    if rejected_at is not None:
        change_set.rejected_at = rejected_at
    change_set.updated_at = datetime.utcnow()
    db.add(change_set)
    db.commit()
    db.refresh(change_set)
    return change_set


def update_change_file(db: DBSession, change_file: ChangeFile, *, proposed_content: str | None = None) -> ChangeFile:
    if proposed_content is not None:
        change_file.proposed_content = proposed_content
    change_file.updated_at = datetime.utcnow()
    db.add(change_file)
    db.commit()
    db.refresh(change_file)
    return change_file
