from datetime import datetime

from sqlmodel import Session as DBSession

from .models import Run


def create_run(db: DBSession, task: str, provider: str, model: str, session_id: int) -> Run:
    run = Run(task=task, provider=provider, model=model, session_id=session_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_run(db: DBSession, run: Run, *, status: str, final_output: str | None = None) -> Run:
    run.status = status
    run.final_output = final_output
    run.updated_at = datetime.utcnow()
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: DBSession, run_id: int) -> Run | None:
    return db.get(Run, run_id)
