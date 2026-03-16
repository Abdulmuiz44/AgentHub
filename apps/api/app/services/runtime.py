import json
from typing import Any

from sqlmodel import Session as DBSession

from app.services.sessions import create_session, get_session_by_id
from app.services.skills import SkillCatalogService
from core.contracts import (
    AgentRequest,
    ApprovalStatus,
    EventType,
    ExecutionBudget,
    ExecutionMode,
    ExecutionState,
    PlanStep,
    PlanningSource,
    RunContext,
    RunStatus,
    TraceEvent,
)
from core.executor import Executor
from core.planner import Planner
from core.planning_service import PlanningService
from core.synthesis import SynthesisEngine
from core.tracing import TraceCollector
from memory import approvals as approval_repo
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import ApprovalRequest, Run, Session, TraceEventRecord


class RunRuntimeService:
    def __init__(self) -> None:
        self.planner = Planner()
        self.planning_service = PlanningService(planner=self.planner)
        self.synthesis_engine = SynthesisEngine()

    @staticmethod
    def persist_trace_events(db: DBSession, run_id: int, events: list[TraceEvent]) -> list[TraceEventRecord]:
        records: list[TraceEventRecord] = []
        for event in events:
            payload = json.dumps(event.payload)
            records.append(trace_repo.add_trace_event(db, run_id, event.event_type.value, payload))
        return records

    def initial_execution_state(self, request: AgentRequest) -> ExecutionState:
        return ExecutionState(
            enabled_skills=list(request.enabled_skills),
            budget=request.budget or ExecutionBudget(),
        )

    def create_run(self, db: DBSession, request: AgentRequest) -> tuple[Run, Session, list[TraceEventRecord]]:
        session = get_session_by_id(db, request.session_id) if request.session_id else None
        if session is None:
            session = create_session(db)

        request.budget = request.budget or ExecutionBudget()
        state = self.initial_execution_state(request)
        run = run_repo.create_run(
            db,
            task=request.task,
            provider=request.provider,
            model=request.model,
            session_id=session.id,
            execution_mode=request.execution_mode.value,
            planning_source=PlanningSource.DETERMINISTIC.value,
            planning_summary="",
            status=RunStatus.QUEUED.value,
            budget_config=request.budget.model_dump(mode="json"),
            execution_state=state.model_dump(mode="json"),
        )
        traces = TraceCollector()
        traces.record_simple(
            run.id,
            EventType.RUN_QUEUED,
            {
                "status": RunStatus.QUEUED.value,
                "execution_mode": request.execution_mode.value,
                "provider": request.provider,
                "model": request.model,
            },
        )
        events = self.persist_trace_events(db, run.id, traces.events())
        return run, session, events

    def load_state(self, run: Run) -> ExecutionState:
        if not run.execution_state:
            return ExecutionState()
        return ExecutionState.model_validate(run.execution_state)

    def process_run(self, db: DBSession, run_id: int) -> Run | None:
        run = run_repo.get_run(db, run_id)
        if run is None or run.status in {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
            return run

        state = self.load_state(run)
        catalog = SkillCatalogService(db)
        registry = catalog.build_registry()
        executor = Executor(skill_registry=registry)
        context = RunContext(run_id=run.id, session_id=run.session_id)

        if run.cancel_requested and run.status in {RunStatus.QUEUED.value, RunStatus.PENDING.value, RunStatus.WAITING_FOR_APPROVAL.value}:
            return self._finalize_cancelled(db, run, state, "Run cancelled before execution resumed.")

        if run.status in {RunStatus.PENDING.value, RunStatus.QUEUED.value}:
            traces = TraceCollector()
            traces.record_simple(
                run.id,
                EventType.RUN_STARTED,
                {"status": RunStatus.RUNNING.value, "context": context.model_dump(mode="json"), "execution_mode": run.execution_mode},
            )
            self.persist_trace_events(db, run.id, traces.events())
            run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value, execution_state=state.model_dump(mode="json"))
        elif run.status == RunStatus.WAITING_FOR_APPROVAL.value:
            approval = approval_repo.get_approval(db, state.pending_approval_id) if state.pending_approval_id else None
            if approval is None or approval.status == ApprovalStatus.PENDING.value:
                return run
            traces = TraceCollector()
            traces.record_simple(
                run.id,
                EventType.APPROVAL_RESOLVED,
                {
                    "approval_id": approval.id,
                    "step_id": approval.step_id,
                    "status": approval.status,
                    "resolution_summary": approval.resolution_summary,
                },
            )
            if approval.status == ApprovalStatus.DENIED.value:
                traces.record_simple(
                    run.id,
                    EventType.RUN_FAILED,
                    {"status": RunStatus.FAILED.value, "output": approval.resolution_summary or "Approval denied."},
                )
                self.persist_trace_events(db, run.id, traces.events())
                state.failure_context = approval.resolution_summary or "Approval denied."
                return run_repo.update_run(
                    db,
                    run,
                    status=RunStatus.FAILED.value,
                    final_output=state.failure_context,
                    execution_summary=executor.build_result(
                        state,
                        execution_mode=ExecutionMode(run.execution_mode),
                        planning_source=PlanningSource(state.planning_source),
                        planning_summary=state.planning_summary,
                        fallback_reason=state.fallback_reason,
                    ).execution_summary,
                    evidence_summary={"items": len(state.evidence.items), "notes": len(state.evidence.notes)},
                    budget_usage_summary=state.budget_usage_summary,
                    execution_state=state.model_dump(mode="json"),
                )
            state.pending_approval_id = None
            traces.record_simple(
                run.id,
                EventType.RUN_RESUMED,
                {"status": RunStatus.RUNNING.value, "approval_id": approval.id, "step_id": approval.step_id},
            )
            self.persist_trace_events(db, run.id, traces.events())
            run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value, execution_state=state.model_dump(mode="json"))

        request = self._build_request(db, run, state, catalog)
        if not state.plan:
            self._plan_run(db, run, state, request)
            run = run_repo.get_run(db, run.id)
            state = self.load_state(run)
            if run.status == RunStatus.WAITING_FOR_APPROVAL.value:
                return run

        while state.current_step_index < len(state.plan):
            run = run_repo.get_run(db, run.id)
            state = self.load_state(run)
            if run.cancel_requested:
                return self._finalize_cancelled(db, run, state, "Run cancelled during execution.")

            step = state.plan[state.current_step_index]
            if step.requires_approval:
                approval = approval_repo.get_pending_approval_for_step(db, run.id, step.id)
                if approval is None:
                    approval = approval_repo.create_approval(db, run_id=run.id, step_id=step.id, reason=step.approval_reason or "Approval required")
                if approval.status == ApprovalStatus.PENDING.value:
                    state.pending_approval_id = approval.id
                    traces = TraceCollector()
                    traces.record_simple(
                        run.id,
                        EventType.APPROVAL_REQUESTED,
                        {"approval_id": approval.id, "step_id": step.id, "reason": approval.reason},
                    )
                    traces.record_simple(
                        run.id,
                        EventType.RUN_PAUSED,
                        {"status": RunStatus.WAITING_FOR_APPROVAL.value, "approval_id": approval.id, "step_id": step.id},
                    )
                    self.persist_trace_events(db, run.id, traces.events())
                    return run_repo.update_run(
                        db,
                        run,
                        status=RunStatus.WAITING_FOR_APPROVAL.value,
                        execution_state=state.model_dump(mode="json"),
                    )
                if approval.status == ApprovalStatus.DENIED.value:
                    state.failure_context = approval.resolution_summary or "Approval denied."
                    traces = TraceCollector()
                    traces.record_simple(
                        run.id,
                        EventType.APPROVAL_RESOLVED,
                        {
                            "approval_id": approval.id,
                            "step_id": approval.step_id,
                            "status": approval.status,
                            "resolution_summary": approval.resolution_summary,
                        },
                    )
                    traces.record_simple(
                        run.id,
                        EventType.RUN_FAILED,
                        {"status": RunStatus.FAILED.value, "output": state.failure_context},
                    )
                    self.persist_trace_events(db, run.id, traces.events())
                    return run_repo.update_run(
                        db,
                        run,
                        status=RunStatus.FAILED.value,
                        final_output=state.failure_context,
                        budget_usage_summary=state.budget_usage_summary,
                        execution_state=state.model_dump(mode="json"),
                    )
                state.pending_approval_id = None

            traces = TraceCollector()
            state = executor.execute_steps(
                context=context,
                steps=state.plan,
                trace_collector=traces,
                budget=state.budget,
                checkpoint=state,
                max_steps=1,
            )
            self.persist_trace_events(db, run.id, traces.events())
            partial = executor.build_result(
                state,
                execution_mode=ExecutionMode(run.execution_mode),
                planning_source=PlanningSource(state.planning_source),
                planning_summary=state.planning_summary,
                fallback_reason=state.fallback_reason,
            )
            run = run_repo.update_run(
                db,
                run,
                status=RunStatus.RUNNING.value,
                final_output=partial.output,
                execution_summary=partial.execution_summary,
                evidence_summary={"items": len(partial.evidence.items), "notes": len(partial.evidence.notes)},
                budget_usage_summary=partial.budget_usage_summary,
                execution_state=state.model_dump(mode="json"),
            )

        final = executor.build_result(
            state,
            execution_mode=ExecutionMode(run.execution_mode),
            planning_source=PlanningSource(state.planning_source),
            planning_summary=state.planning_summary,
            fallback_reason=state.fallback_reason,
        )
        return self._finalize_completed_run(db, run, state, final)

    def _build_request(self, db: DBSession, run: Run, state: ExecutionState, catalog: SkillCatalogService) -> AgentRequest:
        enabled_skills = list(state.enabled_skills)
        available_skills = catalog.list_enabled_skill_names()
        if enabled_skills:
            available_skills = [name for name in available_skills if name in enabled_skills]
        planning_skills = catalog.list_planning_skills(allowed_names=enabled_skills or None)
        return AgentRequest(
            task=run.task,
            session_id=run.session_id,
            provider=run.provider,
            model=run.model,
            enabled_skills=enabled_skills,
            available_skills=available_skills,
            planning_skills=planning_skills,
            execution_mode=ExecutionMode(run.execution_mode),
            budget=state.budget,
        )

    def _plan_run(self, db: DBSession, run: Run, state: ExecutionState, request: AgentRequest) -> None:
        traces = TraceCollector()
        traces.record_simple(
            run.id,
            EventType.PLANNING_STARTED,
            {
                "execution_mode": request.execution_mode.value,
                "provider": request.provider,
                "model": request.model,
                "eligible_skills": [item.model_dump(mode="json") for item in request.planning_skills],
            },
        )
        planning = self.planning_service.create_plan(request)
        state.plan = self._annotate_plan_for_approvals(planning.plan, request.planning_skills)
        state.planning_source = planning.planning_source
        state.planning_summary = planning.planning_summary
        state.fallback_reason = planning.fallback_reason
        if planning.validation_error:
            traces.record_simple(
                run.id,
                EventType.PLAN_VALIDATION_FAILED,
                {"execution_mode": request.execution_mode.value, "error": planning.validation_error},
            )
        if planning.fallback_reason:
            traces.record_simple(
                run.id,
                EventType.PLANNING_FALLBACK,
                {
                    "execution_mode": request.execution_mode.value,
                    "fallback_reason": planning.fallback_reason,
                    "planning_source": planning.planning_source.value,
                },
            )
        traces.record_simple(
            run.id,
            EventType.PLAN_CREATED,
            {
                "plan": [item.model_dump(mode="json") for item in state.plan],
                "requested_skills": request.enabled_skills,
                "execution_mode": request.execution_mode.value,
                "planning_source": planning.planning_source.value,
                "planning_summary": planning.planning_summary,
                "fallback_reason": planning.fallback_reason,
            },
        )
        self.persist_trace_events(db, run.id, traces.events())
        run_repo.update_run(
            db,
            run,
            status=RunStatus.RUNNING.value,
            planning_source=planning.planning_source.value,
            planning_summary=planning.planning_summary,
            fallback_reason=planning.fallback_reason,
            budget_config=state.budget.model_dump(mode="json"),
            execution_state=state.model_dump(mode="json"),
        )

    @staticmethod
    def _annotate_plan_for_approvals(plan: list[PlanStep], planning_skills: list[Any]) -> list[PlanStep]:
        descriptors = {item.name: item for item in planning_skills}
        annotated: list[PlanStep] = []
        for step in plan:
            copy = step.model_copy(deep=True)
            descriptor = descriptors.get(step.skill_name or "")
            if descriptor is not None and descriptor.approval_required:
                copy.requires_approval = True
                copy.approval_reason = f"Skill {descriptor.name} requires approval before execution."
            annotated.append(copy)
        return annotated

    def _finalize_completed_run(self, db: DBSession, run: Run, state: ExecutionState, final_result) -> Run:
        traces = TraceCollector()
        traces.record_simple(
            run.id,
            EventType.SYNTHESIS_STARTED,
            {"provider": run.provider, "model": run.model, "evidence_items": len(final_result.evidence.items)},
        )
        synthesis_output, synthesis_meta = self.synthesis_engine.synthesize(
            task=run.task,
            provider=run.provider,
            model=run.model,
            plan=final_result.plan,
            step_results=final_result.step_results,
            execution_summary=final_result.execution_summary,
            evidence=final_result.evidence,
        )
        if synthesis_meta.mode == "deterministic_fallback" and synthesis_meta.error_summary:
            traces.record_simple(
                run.id,
                EventType.SYNTHESIS_FAILED,
                {
                    "provider": run.provider,
                    "model": run.model,
                    "error": synthesis_meta.error_summary,
                    "fallback_mode": synthesis_meta.mode,
                },
            )
        traces.record_simple(
            run.id,
            EventType.SYNTHESIS_COMPLETED,
            {
                "mode": synthesis_meta.mode,
                "status": synthesis_meta.status,
                "provider": synthesis_meta.provider,
                "provider_status": synthesis_meta.provider_status,
                "model": synthesis_meta.model,
                "usage": synthesis_meta.provider_usage_summary,
                "execution_summary": final_result.execution_summary,
                "evidence_summary": {"items": len(final_result.evidence.items), "notes": len(final_result.evidence.notes)},
            },
        )
        terminal_event = EventType.RUN_COMPLETED if final_result.status == RunStatus.COMPLETED else EventType.RUN_FAILED
        traces.record_simple(run.id, terminal_event, {"status": final_result.status.value, "output": synthesis_output})
        self.persist_trace_events(db, run.id, traces.events())
        return run_repo.update_run(
            db,
            run,
            status=final_result.status.value,
            cancel_requested=False,
            final_output=synthesis_output,
            synthesis_mode=synthesis_meta.mode,
            synthesis_status=synthesis_meta.status,
            synthesis_error_summary=synthesis_meta.error_summary,
            execution_summary=final_result.execution_summary,
            evidence_summary={"items": len(final_result.evidence.items), "notes": len(final_result.evidence.notes)},
            planning_source=final_result.planning_source.value,
            planning_summary=final_result.planning_summary,
            fallback_reason=final_result.fallback_reason,
            budget_config=final_result.budget_config,
            budget_usage_summary=final_result.budget_usage_summary,
            execution_state=state.model_dump(mode="json"),
        )

    def _finalize_cancelled(self, db: DBSession, run: Run, state: ExecutionState, summary: str) -> Run:
        traces = TraceCollector()
        traces.record_simple(run.id, EventType.RUN_CANCELLED, {"status": RunStatus.CANCELLED.value, "summary": summary})
        self.persist_trace_events(db, run.id, traces.events())
        return run_repo.update_run(
            db,
            run,
            status=RunStatus.CANCELLED.value,
            cancel_requested=False,
            final_output=summary,
            evidence_summary={"items": len(state.evidence.items), "notes": len(state.evidence.notes)},
            budget_usage_summary=state.budget_usage_summary,
            execution_state=state.model_dump(mode="json"),
        )

    @staticmethod
    def serialize_run(db: DBSession, run: Run) -> dict[str, Any]:
        pending_approval = approval_repo.get_latest_pending_approval(db, run.id)
        return {
            "id": run.id,
            "session_id": run.session_id,
            "task": run.task,
            "provider": run.provider,
            "model": run.model,
            "execution_mode": run.execution_mode,
            "planning_source": run.planning_source,
            "planning_summary": run.planning_summary,
            "fallback_reason": run.fallback_reason,
            "status": run.status,
            "cancel_requested": run.cancel_requested,
            "final_output": run.final_output,
            "synthesis_mode": run.synthesis_mode,
            "synthesis_status": run.synthesis_status,
            "synthesis_error_summary": run.synthesis_error_summary,
            "execution_summary": run.execution_summary,
            "evidence_summary": run.evidence_summary,
            "budget_config": run.budget_config,
            "budget_usage_summary": run.budget_usage_summary,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "pending_approval": self_serialize_approval(pending_approval) if pending_approval is not None else None,
        }


def self_serialize_approval(approval: ApprovalRequest) -> dict[str, Any]:
    return {
        "id": approval.id,
        "run_id": approval.run_id,
        "step_id": approval.step_id,
        "reason": approval.reason,
        "status": approval.status,
        "resolution_summary": approval.resolution_summary,
        "created_at": approval.created_at,
        "updated_at": approval.updated_at,
    }
