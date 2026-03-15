import json
from typing import Any

from sqlmodel import Session as DBSession

from app.config import settings
from app.services.sessions import create_session, get_session_by_id
from core.contracts import AgentRequest, EventType, RunContext, RunStatus, TraceEvent
from core.executor import Executor
from core.planner import Planner
from core.task_runner import TaskRunner
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import Run, Session, TraceEventRecord
from models.registry import ProviderRegistry
from skills.registry import SkillRegistry


def _persist_trace_events(db: DBSession, run_id: int, events: list[TraceEvent]) -> list[TraceEventRecord]:
    records: list[TraceEventRecord] = []
    for event in events:
        payload = json.dumps(event.payload)
        records.append(trace_repo.add_trace_event(db, run_id, event.event_type.value, payload))
    return records


def _resolve_provider_config(provider: str) -> tuple[bool, dict[str, Any]]:
    if provider == "openai":
        return bool(settings.openai_api_key), {
            "api_key": settings.openai_api_key,
            "base_url": settings.openai_base_url,
            "default_model": settings.openai_default_model,
        }
    if provider == "ollama":
        return bool(settings.ollama_base_url), {
            "base_url": settings.ollama_base_url,
            "default_model": settings.ollama_default_model,
        }
    return True, {}


def _synthesize_output(request: AgentRequest, run_id: int, deterministic_output: str) -> tuple[list[TraceEvent], dict[str, Any]]:
    metadata: dict[str, Any] = {
        "synthesis_enabled": request.provider != "builtin",
        "synthesis_provider": request.provider,
        "synthesis_model": request.model,
        "synthesis_status": "skipped",
        "synthesis_output": None,
    }
    if request.provider == "builtin":
        return [
            TraceEvent(
                run_id=run_id,
                event_type=EventType.SYNTHESIS_SKIPPED,
                payload={"reason": "builtin_provider", "provider": request.provider},
            )
        ], metadata

    registry = ProviderRegistry.default()
    adapter = registry.get(request.provider)
    if adapter is None:
        metadata["synthesis_status"] = "skipped"
        return [
            TraceEvent(
                run_id=run_id,
                event_type=EventType.SYNTHESIS_SKIPPED,
                payload={"reason": "provider_not_registered", "provider": request.provider},
            )
        ], metadata

    config_ok, provider_config = _resolve_provider_config(request.provider)
    if not config_ok:
        metadata["synthesis_status"] = "skipped"
        return [
            TraceEvent(
                run_id=run_id,
                event_type=EventType.SYNTHESIS_SKIPPED,
                payload={"reason": "missing_provider_config", "provider": request.provider},
            )
        ], metadata

    model = request.model
    if model == "deterministic":
        model = provider_config.get("default_model") or model
    metadata["synthesis_model"] = model

    prompt = (
        "You are generating a concise final answer from deterministic tool execution results.\n"
        f"Task: {request.task}\n"
        f"Execution summary:\n{deterministic_output}\n"
    )
    traces = [
        TraceEvent(
            run_id=run_id,
            event_type=EventType.SYNTHESIS_REQUESTED,
            payload={"provider": request.provider, "model": model},
        )
    ]
    try:
        synthesized = adapter.generate(prompt=prompt, model=model)
        metadata["synthesis_status"] = "completed"
        metadata["synthesis_output"] = synthesized
        traces.append(
            TraceEvent(
                run_id=run_id,
                event_type=EventType.SYNTHESIS_COMPLETED,
                payload={"provider": request.provider, "model": model, "output": synthesized[:300]},
            )
        )
    except Exception as exc:  # pragma: no cover - defensive fallback
        metadata["synthesis_status"] = "failed"
        traces.append(
            TraceEvent(
                run_id=run_id,
                event_type=EventType.SYNTHESIS_FAILED,
                payload={"provider": request.provider, "model": model, "error": str(exc)},
            )
        )
    return traces, metadata


def create_run(
    db: DBSession,
    request: AgentRequest,
    *,
    execute_now: bool = True,
) -> tuple[Run, Session, list[TraceEventRecord], dict[str, Any]]:
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

    if not execute_now:
        run = run_repo.update_run(db, run, status=RunStatus.PENDING.value)
        return run, session, [], {"synthesis_status": "not_executed"}

    run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value)

    context = RunContext(run_id=run.id, session_id=session.id)
    registry = SkillRegistry.default(workspace_root=settings.workspace_root)
    runner = TaskRunner(planner=Planner(), executor=Executor(skill_registry=registry))

    result, events = runner.run(request, context)
    synthesis_events, metadata = _synthesize_output(request, run.id, result.output)
    events.extend(synthesis_events)

    terminal = EventType.RUN_COMPLETED if result.status.value == "completed" else EventType.RUN_FAILED
    events.append(TraceEvent(run_id=run.id, event_type=terminal, payload={"status": result.status.value, "output": result.output}))

    persisted_events = _persist_trace_events(db, run.id, events)
    run = run_repo.update_run(db, run, status=result.status.value, final_output=result.output)

    return run, session, persisted_events, metadata


def get_run(db: DBSession, run_id: int) -> Run | None:
    return run_repo.get_run(db, run_id)


def list_trace(db: DBSession, run_id: int) -> list[TraceEventRecord]:
    return trace_repo.list_trace_events(db, run_id)
