import json

from sqlmodel import Session as DBSession

from core.contracts import AgentRequest, EventType, PlanStep, RunContext, RunStatus
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import Run, Session, TraceEventRecord
from app.services.sessions import create_session, get_session_by_id


def create_run(
    db: DBSession,
    request: AgentRequest,
) -> tuple[Run, Session, list[TraceEventRecord]]:
    session = get_session_by_id(db, request.session_id) if request.session_id else None
    if session is None:
        session = create_session(db)

    run = run_repo.create_run(
        db,
        task=request.task,
        provider=request.provider,
        model=request.model,
        session_id=session.id,
    )

    context = RunContext(run_id=run.id, session_id=session.id)
    started_payload = json.dumps({"status": RunStatus.RUNNING.value, "context": context.model_dump(mode="json")})
    plan_payload = json.dumps(
        {
            "plan": [PlanStep(id="step-1", title="placeholder planning step").model_dump(mode="json")],
            "requested_skills": request.enabled_skills,
        }
    )
    events = [
        trace_repo.add_trace_event(db, run.id, EventType.RUN_STARTED.value, started_payload),
        trace_repo.add_trace_event(db, run.id, EventType.PLAN_CREATED.value, plan_payload),
    ]
    run.status = RunStatus.RUNNING.value
    db.add(run)
    db.commit()
    db.refresh(run)
    return run, session, events


def get_run(db: DBSession, run_id: int) -> Run | None:
    return run_repo.get_run(db, run_id)


def list_trace(db: DBSession, run_id: int) -> list[TraceEventRecord]:
    return trace_repo.list_trace_events(db, run_id)
