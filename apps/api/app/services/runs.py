from typing import Any

from sqlmodel import Session as DBSession

from app.services.change_review import ChangeReviewError
from app.services.runtime import RunRuntimeService, self_serialize_approval
from core.contracts import AgentRequest, ApprovalStatus, EventType, RunStatus
from core.tracing import TraceCollector
from memory import approvals as approval_repo
from memory import changes as change_repo
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import Run, Session, TraceEventRecord

runtime_service = RunRuntimeService()


def create_run(db: DBSession, request: AgentRequest) -> tuple[Run, Session, list[TraceEventRecord]]:
    return runtime_service.create_run(db, request)


def get_run(db: DBSession, run_id: int) -> Run | None:
    return run_repo.get_run(db, run_id)


def get_run_response(db: DBSession, run_id: int) -> dict[str, Any] | None:
    run = get_run(db, run_id)
    if run is None:
        return None
    return runtime_service.serialize_run(db, run)


def list_trace(db: DBSession, run_id: int, *, after_id: int = 0) -> list[TraceEventRecord]:
    return trace_repo.list_trace_events(db, run_id, after_id=after_id)


def list_changes(db: DBSession, run_id: int) -> list[dict[str, Any]] | None:
    run = get_run(db, run_id)
    if run is None:
        return None
    return runtime_service.list_changes(db, run_id)


def cancel_run(db: DBSession, run_id: int) -> dict[str, Any] | None:
    run = get_run(db, run_id)
    if run is None:
        return None

    traces = TraceCollector()
    traces.record_simple(run.id, EventType.RUN_CANCEL_REQUESTED, {"status": run.status})
    runtime_service.persist_trace_events(db, run.id, traces.events())

    if run.status in {RunStatus.QUEUED.value, RunStatus.PENDING.value, RunStatus.WAITING_FOR_APPROVAL.value}:
        state = runtime_service.load_state(run)
        run = run_repo.update_run(db, run, cancel_requested=True, execution_state=state.model_dump(mode="json"))
        run = runtime_service.process_run(db, run.id) or run
        return runtime_service.serialize_run(db, run)

    run = run_repo.update_run(db, run, cancel_requested=True)
    return runtime_service.serialize_run(db, run)


def resolve_approval(db: DBSession, run_id: int, approval_id: int, *, status: ApprovalStatus, summary: str | None = None) -> tuple[dict[str, Any], dict[str, Any]] | None:
    run = get_run(db, run_id)
    if run is None:
        return None
    approval = approval_repo.get_approval(db, approval_id)
    if approval is None or approval.run_id != run_id:
        return None
    approval = approval_repo.update_approval(db, approval, status=status.value, resolution_summary=summary)
    return runtime_service.serialize_run(db, run), self_serialize_approval(approval)


def apply_run_changes(db: DBSession, run_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    run = get_run(db, run_id)
    if run is None:
        return None
    applied = runtime_service.apply_pending_changes(db, run_id)
    if applied is None:
        return None
    change_set = change_repo.get_pending_change_set_for_run(db, run_id)
    if change_set is None:
        sets = change_repo.list_change_sets_for_run(db, run_id)
        change_set = sets[-1] if sets else None
    if change_set is None:
        raise ChangeReviewError("Change set history is unavailable")
    files = [runtime_service.change_review_service.serialize_change_file(item) for item in change_repo.list_change_files(db, change_set.id)]
    return runtime_service.serialize_run(db, applied), runtime_service.change_review_service.serialize_change_set(change_set, files)


def reject_run_changes(db: DBSession, run_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    run = get_run(db, run_id)
    if run is None:
        return None
    rejected = runtime_service.reject_pending_changes(db, run_id)
    if rejected is None:
        return None
    sets = change_repo.list_change_sets_for_run(db, run_id)
    change_set = sets[-1] if sets else None
    if change_set is None:
        raise ChangeReviewError("Change set history is unavailable")
    files = [runtime_service.change_review_service.serialize_change_file(item) for item in change_repo.list_change_files(db, change_set.id)]
    return runtime_service.serialize_run(db, rejected), runtime_service.change_review_service.serialize_change_set(change_set, files)
