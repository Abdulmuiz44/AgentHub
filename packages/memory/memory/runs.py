from datetime import datetime
from typing import Any

from sqlmodel import Session as DBSession

from .models import Run


def create_run(db: DBSession, task: str, provider: str, model: str, session_id: int) -> Run:
    run = Run(task=task, provider=provider, model=model, session_id=session_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_run(
    db: DBSession,
    run: Run,
    *,
    status: str,
    final_output: str | None = None,
    synthesis_mode: str | None = None,
    synthesis_status: str | None = None,
    synthesis_error_summary: str | None = None,
    execution_summary: dict[str, Any] | None = None,
    evidence_summary: dict[str, Any] | None = None,
) -> Run:
    run.status = status
    run.final_output = final_output
    run.synthesis_mode = synthesis_mode
    run.synthesis_status = synthesis_status
    run.synthesis_error_summary = synthesis_error_summary
    run.execution_summary = execution_summary or {}
    run.evidence_summary = evidence_summary or {}
    run.updated_at = datetime.utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: DBSession, run_id: int) -> Run | None:
    return db.get(Run, run_id)
