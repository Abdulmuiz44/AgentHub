import json

from sqlmodel import Session as DBSession

from app.services.sessions import create_session, get_session_by_id
from app.services.skills import SkillCatalogService
from core.contracts import AgentRequest, RunContext, RunStatus, TraceEvent
from core.executor import Executor
from core.planner import Planner
from core.task_runner import TaskRunner
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import Run, Session, TraceEventRecord


def _persist_trace_events(db: DBSession, run_id: int, events: list[TraceEvent]) -> list[TraceEventRecord]:
    records: list[TraceEventRecord] = []
    for event in events:
        payload = json.dumps(event.payload)
        records.append(trace_repo.add_trace_event(db, run_id, event.event_type.value, payload))
    return records


def create_run(db: DBSession, request: AgentRequest, *, execute_now: bool = True) -> tuple[Run, Session, list[TraceEventRecord]]:
    session = get_session_by_id(db, request.session_id) if request.session_id else None
    if session is None:
        session = create_session(db)

    catalog = SkillCatalogService(db)
    request.available_skills = catalog.list_enabled_skill_names()
    registry = catalog.build_registry()

    run = run_repo.create_run(db, task=request.task, provider=request.provider, model=request.model, session_id=session.id)

    if not execute_now:
        run = run_repo.update_run(db, run, status=RunStatus.PENDING.value)
        return run, session, []

    run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value)

    context = RunContext(run_id=run.id, session_id=session.id)
    runner = TaskRunner(planner=Planner(), executor=Executor(skill_registry=registry))

    result, events = runner.run(request, context)
    persisted_events = _persist_trace_events(db, run.id, events)
    run = run_repo.update_run(
        db,
        run,
        status=result.status.value,
        final_output=result.output,
        synthesis_mode=result.synthesis.mode if result.synthesis else None,
        synthesis_status=result.synthesis.status if result.synthesis else None,
        synthesis_error_summary=result.synthesis.error_summary if result.synthesis else None,
        execution_summary=result.execution_summary,
        evidence_summary={"items": len(result.evidence.items), "notes": len(result.evidence.notes)},
    )

    return run, session, persisted_events


def get_run(db: DBSession, run_id: int) -> Run | None:
    return run_repo.get_run(db, run_id)


def list_trace(db: DBSession, run_id: int) -> list[TraceEventRecord]:
    return trace_repo.list_trace_events(db, run_id)
