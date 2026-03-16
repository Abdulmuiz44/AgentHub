from datetime import datetime
from typing import Any

from sqlmodel import Session as DBSession, select

from .models import Run

_UNSET = object()


def create_run(
    db: DBSession,
    task: str,
    provider: str,
    model: str,
    session_id: int,
    *,
    execution_mode: str = "deterministic",
    planning_source: str = "deterministic",
    planning_summary: str = "",
    fallback_reason: str | None = None,
    status: str = "pending",
    budget_config: dict[str, Any] | None = None,
    execution_state: dict[str, Any] | None = None,
) -> Run:
    run = Run(
        task=task,
        provider=provider,
        model=model,
        session_id=session_id,
        execution_mode=execution_mode,
        planning_source=planning_source,
        planning_summary=planning_summary,
        fallback_reason=fallback_reason,
        status=status,
        budget_config=budget_config or {},
        execution_state=execution_state or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: DBSession,
    run: Run,
    *,
    status: str | None = None,
    cancel_requested: bool | None = None,
    final_output: str | None | object = _UNSET,
    synthesis_mode: str | None | object = _UNSET,
    synthesis_status: str | None | object = _UNSET,
    synthesis_error_summary: str | None | object = _UNSET,
    execution_summary: dict[str, Any] | object = _UNSET,
    evidence_summary: dict[str, Any] | object = _UNSET,
    planning_source: str | None | object = _UNSET,
    planning_summary: str | None | object = _UNSET,
    fallback_reason: str | None | object = _UNSET,
    budget_config: dict[str, Any] | object = _UNSET,
    budget_usage_summary: dict[str, Any] | object = _UNSET,
    execution_state: dict[str, Any] | object = _UNSET,
) -> Run:
    if status is not None:
        run.status = status
    if cancel_requested is not None:
        run.cancel_requested = cancel_requested
    if final_output is not _UNSET:
        run.final_output = final_output
    if synthesis_mode is not _UNSET:
        run.synthesis_mode = synthesis_mode
    if synthesis_status is not _UNSET:
        run.synthesis_status = synthesis_status
    if synthesis_error_summary is not _UNSET:
        run.synthesis_error_summary = synthesis_error_summary
    if execution_summary is not _UNSET:
        run.execution_summary = execution_summary
    if evidence_summary is not _UNSET:
        run.evidence_summary = evidence_summary
    if planning_source is not _UNSET:
        run.planning_source = planning_source
    if planning_summary is not _UNSET:
        run.planning_summary = planning_summary
    if fallback_reason is not _UNSET:
        run.fallback_reason = fallback_reason
    if budget_config is not _UNSET:
        run.budget_config = budget_config
    if budget_usage_summary is not _UNSET:
        run.budget_usage_summary = budget_usage_summary
    if execution_state is not _UNSET:
        run.execution_state = execution_state
    run.updated_at = datetime.utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: DBSession, run_id: int) -> Run | None:
    return db.get(Run, run_id)


def list_runs_by_status(db: DBSession, statuses: list[str]) -> list[Run]:
    statement = select(Run).where(Run.status.in_(statuses)).order_by(Run.id)
    return db.exec(statement).all()
