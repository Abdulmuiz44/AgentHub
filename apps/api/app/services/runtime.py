import json
from typing import Any

from sqlmodel import Session as DBSession

from app.config import settings
from app.services.change_review import ChangeReviewError, ChangeReviewService
from app.services.sessions import create_session, get_session_by_id
from app.services.skills import SkillCatalogService
from core.contracts import (
    AgentRequest,
    ApprovalStatus,
    EventType,
    ExecutionBudget,
    ExecutionMode,
    ExecutionState,
    MutationApplyMode,
    PlanStep,
    PlanningSource,
    ReviewStatus,
    RunContext,
    RunStatus,
    StepExecutionResult,
    TraceEvent,
)
from core.executor import Executor
from core.planning_service import PlanningService
from core.synthesis import SynthesisEngine
from core.tracing import TraceCollector
from memory import approvals as approval_repo
from memory import changes as change_repo
from memory import runs as run_repo
from memory import traces as trace_repo
from memory.models import ApprovalRequest, Run, Session, TraceEventRecord
from skills.base import SkillRequest


class RunRuntimeService:
    def __init__(self) -> None:
        self.planning_service = PlanningService()
        self.synthesis_engine = SynthesisEngine()
        self.change_review_service = ChangeReviewService(settings.workspace_root)

    @staticmethod
    def persist_trace_events(db: DBSession, run_id: int, events: list[TraceEvent]) -> list[TraceEventRecord]:
        records: list[TraceEventRecord] = []
        for event in events:
            payload = json.dumps(event.payload)
            records.append(trace_repo.add_trace_event(db, run_id, event.event_type.value, payload))
        return records

    def initial_execution_state(self, request: AgentRequest) -> ExecutionState:
        return ExecutionState(enabled_skills=list(request.enabled_skills), budget=request.budget or ExecutionBudget())

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
            mutation_apply_mode=request.mutation_apply_mode.value,
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
                "mutation_apply_mode": request.mutation_apply_mode.value,
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
        context = RunContext(run_id=run.id, session_id=run.session_id, workspace_root=settings.workspace_root)

        if run.cancel_requested and run.status in {RunStatus.QUEUED.value, RunStatus.PENDING.value, RunStatus.WAITING_FOR_APPROVAL.value}:
            return self._finalize_cancelled(db, run, state, "Run cancelled before execution resumed.")

        if run.status in {RunStatus.PENDING.value, RunStatus.QUEUED.value}:
            traces = TraceCollector()
            traces.record_simple(
                run.id,
                EventType.RUN_STARTED,
                {"status": RunStatus.RUNNING.value, "context": context.model_dump(mode="json"), "execution_mode": run.execution_mode, "mutation_apply_mode": run.mutation_apply_mode},
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
                traces.record_simple(run.id, EventType.RUN_FAILED, {"status": RunStatus.FAILED.value, "output": approval.resolution_summary or "Approval denied."})
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
            traces.record_simple(run.id, EventType.RUN_RESUMED, {"status": RunStatus.RUNNING.value, "approval_id": approval.id, "step_id": approval.step_id})
            self.persist_trace_events(db, run.id, traces.events())
            run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value, execution_state=state.model_dump(mode="json"))
        elif run.status == RunStatus.WAITING_FOR_REVIEW.value:
            return run

        request = self._build_request(run, state, catalog)
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
                    traces.record_simple(run.id, EventType.APPROVAL_REQUESTED, {"approval_id": approval.id, "step_id": step.id, "reason": approval.reason})
                    traces.record_simple(run.id, EventType.RUN_PAUSED, {"status": RunStatus.WAITING_FOR_APPROVAL.value, "approval_id": approval.id, "step_id": step.id})
                    self.persist_trace_events(db, run.id, traces.events())
                    return run_repo.update_run(db, run, status=RunStatus.WAITING_FOR_APPROVAL.value, execution_state=state.model_dump(mode="json"))
                if approval.status == ApprovalStatus.DENIED.value:
                    state.failure_context = approval.resolution_summary or "Approval denied."
                    traces = TraceCollector()
                    traces.record_simple(run.id, EventType.APPROVAL_RESOLVED, {"approval_id": approval.id, "step_id": approval.step_id, "status": approval.status, "resolution_summary": approval.resolution_summary})
                    traces.record_simple(run.id, EventType.RUN_FAILED, {"status": RunStatus.FAILED.value, "output": state.failure_context})
                    self.persist_trace_events(db, run.id, traces.events())
                    return run_repo.update_run(db, run, status=RunStatus.FAILED.value, final_output=state.failure_context, budget_usage_summary=state.budget_usage_summary, execution_state=state.model_dump(mode="json"))
                state.pending_approval_id = None

            if self._should_capture_review_first(run, registry.get_skill(step.skill_name or "")):
                run = self._execute_review_first_step(db, run, state, step, registry.get_skill(step.skill_name or ""))
                if run.status == RunStatus.WAITING_FOR_REVIEW.value:
                    return run
                state = self.load_state(run)
                continue

            traces = TraceCollector()
            state = executor.execute_steps(context=context, steps=state.plan, trace_collector=traces, budget=state.budget, checkpoint=state, max_steps=1)
            self.persist_trace_events(db, run.id, traces.events())
            partial = executor.build_result(state, execution_mode=ExecutionMode(run.execution_mode), planning_source=PlanningSource(state.planning_source), planning_summary=state.planning_summary, fallback_reason=state.fallback_reason)
            run = run_repo.update_run(db, run, status=RunStatus.RUNNING.value, final_output=partial.output, execution_summary=partial.execution_summary, evidence_summary={"items": len(partial.evidence.items), "notes": len(partial.evidence.notes)}, budget_usage_summary=partial.budget_usage_summary, execution_state=state.model_dump(mode="json"))

        final = executor.build_result(state, execution_mode=ExecutionMode(run.execution_mode), planning_source=PlanningSource(state.planning_source), planning_summary=state.planning_summary, fallback_reason=state.fallback_reason)
        if state.pending_change_count > 0 and state.pending_change_set_id:
            return self._finalize_review_pending_run(db, run, state, final)
        return self._finalize_completed_run(db, run, state, final)

    def _build_request(self, run: Run, state: ExecutionState, catalog: SkillCatalogService) -> AgentRequest:
        enabled_skills = list(state.enabled_skills)
        available_skills = catalog.list_enabled_skill_names()
        if enabled_skills:
            available_skills = [name for name in available_skills if name in enabled_skills]
        planning_skills = catalog.list_planning_skills(allowed_names=enabled_skills or None)
        return AgentRequest(task=run.task, session_id=run.session_id, provider=run.provider, model=run.model, enabled_skills=enabled_skills, available_skills=available_skills, planning_skills=planning_skills, execution_mode=ExecutionMode(run.execution_mode), mutation_apply_mode=MutationApplyMode(run.mutation_apply_mode), budget=state.budget)

    def _plan_run(self, db: DBSession, run: Run, state: ExecutionState, request: AgentRequest) -> None:
        traces = TraceCollector()
        traces.record_simple(
            run.id,
            EventType.PLANNING_STARTED,
            {
                "execution_mode": request.execution_mode.value,
                "mutation_apply_mode": request.mutation_apply_mode.value,
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
            traces.record_simple(run.id, EventType.PLAN_VALIDATION_FAILED, {"execution_mode": request.execution_mode.value, "error": planning.validation_error})
        if planning.fallback_reason:
            traces.record_simple(run.id, EventType.PLANNING_FALLBACK, {"execution_mode": request.execution_mode.value, "fallback_reason": planning.fallback_reason, "planning_source": planning.planning_source.value})
        traces.record_simple(
            run.id,
            EventType.PLAN_CREATED,
            {
                "plan": [item.model_dump(mode="json") for item in state.plan],
                "requested_skills": request.enabled_skills,
                "execution_mode": request.execution_mode.value,
                "mutation_apply_mode": request.mutation_apply_mode.value,
                "planning_source": planning.planning_source.value,
                "planning_summary": planning.planning_summary,
                "fallback_reason": planning.fallback_reason,
            },
        )
        self.persist_trace_events(db, run.id, traces.events())
        run_repo.update_run(db, run, status=RunStatus.RUNNING.value, planning_source=planning.planning_source.value, planning_summary=planning.planning_summary, fallback_reason=planning.fallback_reason, budget_config=state.budget.model_dump(mode="json"), execution_state=state.model_dump(mode="json"))

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

    def _execute_review_first_step(self, db: DBSession, run: Run, state: ExecutionState, step: PlanStep, skill: Any | None) -> Run:
        traces = TraceCollector()
        if skill is None:
            error = f"Skill not registered: {step.skill_name}"
            traces.record_simple(run.id, EventType.TOOL_FAILED, {"step_id": step.id, "skill": step.skill_name, "error": error})
            self.persist_trace_events(db, run.id, traces.events())
            state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=error, error=error))
            state.current_step_index += 1
            return run_repo.update_run(db, run, execution_state=state.model_dump(mode="json"))

        budget_error = self._check_budget(state, step.skill_name or "")
        traces.record_simple(run.id, EventType.TOOL_REQUESTED, {"step_id": step.id, "skill": step.skill_name, "runtime_type": skill.manifest.runtime_type.value, "input": step.skill_input})
        if budget_error:
            traces.record_simple(run.id, EventType.BUDGET_ENFORCED, {"step_id": step.id, "skill": step.skill_name, "reason": budget_error, "usage": state.budget_usage_summary})
            traces.record_simple(run.id, EventType.TOOL_FAILED, {"step_id": step.id, "skill": step.skill_name, "error": budget_error})
            self.persist_trace_events(db, run.id, traces.events())
            state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=budget_error, error=budget_error))
            state.current_step_index += 1
            return run_repo.update_run(db, run, execution_state=state.model_dump(mode="json"), budget_usage_summary=state.budget_usage_summary)

        traces.record_simple(run.id, EventType.TOOL_STARTED, {"step_id": step.id, "skill": step.skill_name, "runtime_type": skill.manifest.runtime_type.value})
        dynamic_input = dict(step.skill_input)
        dynamic_input["_agenthub_mutation_mode"] = MutationApplyMode.REVIEW_FIRST.value
        result = skill.execute(SkillRequest(operation=dynamic_input.get("operation"), input=dynamic_input))
        self._record_budget_usage(state, step.skill_name or "")
        if not result.success:
            traces.record_simple(run.id, EventType.TOOL_FAILED, {"step_id": step.id, "skill": step.skill_name, "error": result.error})
            self.persist_trace_events(db, run.id, traces.events())
            state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=result.error or "Tool failed", error=result.error))
            state.current_step_index += 1
            return run_repo.update_run(db, run, execution_state=state.model_dump(mode="json"), budget_usage_summary=state.budget_usage_summary)

        raw_changes = result.output.get("file_changes")
        if not isinstance(raw_changes, list) or not raw_changes:
            error = f"Mutation skill {step.skill_name} did not return reviewable file changes"
            traces.record_simple(run.id, EventType.TOOL_FAILED, {"step_id": step.id, "skill": step.skill_name, "error": error})
            self.persist_trace_events(db, run.id, traces.events())
            state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=error, error=error))
            state.current_step_index += 1
            return run_repo.update_run(db, run, execution_state=state.model_dump(mode="json"), budget_usage_summary=state.budget_usage_summary)

        capture = self.change_review_service.capture_proposed_changes(db, run.id, step.id, step.skill_name or "unknown", raw_changes)
        state.step_results.append(StepExecutionResult(step_id=step.id, success=True, summary=f"Proposed {capture['pending_change_count']} file change(s)", output=capture))
        state.current_step_index = len(state.plan)
        state.pending_change_set_id = capture["change_set_id"]
        state.pending_change_count = capture["pending_change_count"]
        state.review_status = ReviewStatus.PENDING
        traces.record_simple(run.id, EventType.TOOL_COMPLETED, {"step_id": step.id, "skill": step.skill_name, "summary": f"Proposed {capture['pending_change_count']} file change(s)", "output": capture})
        traces.record_simple(run.id, EventType.CHANGE_PROPOSED, {"change_set_id": capture["change_set_id"], "files": capture["files"], "step_id": step.id})
        traces.record_simple(run.id, EventType.CHANGE_REVIEW_PENDING, {"change_set_id": capture["change_set_id"], "pending_change_count": capture["pending_change_count"]})
        self.persist_trace_events(db, run.id, traces.events())
        updated = run_repo.update_run(db, run, pending_change_count=capture["pending_change_count"], review_status=ReviewStatus.PENDING.value, budget_usage_summary=state.budget_usage_summary, execution_state=state.model_dump(mode="json"))
        final_result = type(
            "ReviewPendingResult",
            (),
            {
                "plan": state.plan,
                "step_results": state.step_results,
                "execution_summary": {"steps_total": len(state.step_results), "steps_success": sum(1 for item in state.step_results if item.success), "steps_failed": sum(1 for item in state.step_results if not item.success), "evidence_items": len(state.evidence.items), "evidence_notes": len(state.evidence.notes)},
                "evidence": state.evidence,
                "planning_source": PlanningSource(state.planning_source),
                "planning_summary": state.planning_summary,
                "fallback_reason": state.fallback_reason,
                "budget_config": state.budget.model_dump(mode="json"),
                "budget_usage_summary": state.budget_usage_summary,
            },
        )()
        return self._finalize_review_pending_run(db, updated, state, final_result)

    def apply_pending_changes(self, db: DBSession, run_id: int) -> Run | None:
        run = run_repo.get_run(db, run_id)
        if run is None:
            return None
        if run.status != RunStatus.WAITING_FOR_REVIEW.value:
            raise ChangeReviewError("Run is not waiting for review")
        change_set = self.change_review_service.get_pending_change_set(db, run.id)
        if change_set is None:
            raise ChangeReviewError("No pending change set is available")

        traces = TraceCollector()
        traces.record_simple(run.id, EventType.CHANGE_APPLY_REQUESTED, {"change_set_id": change_set.id, "pending_change_count": run.pending_change_count})
        try:
            result = self.change_review_service.apply_change_set(db, change_set)
        except ChangeReviewError as exc:
            self.change_review_service.mark_apply_failed(db, change_set, str(exc))
            traces.record_simple(run.id, EventType.CHANGE_APPLY_FAILED, {"change_set_id": change_set.id, "error": str(exc)})
            self.persist_trace_events(db, run.id, traces.events())
            raise

        traces.record_simple(run.id, EventType.CHANGE_APPLIED, {"change_set_id": change_set.id, **result})
        traces.record_simple(run.id, EventType.RUN_COMPLETED, {"status": RunStatus.COMPLETED.value, "output": result["summary"]})
        self.persist_trace_events(db, run.id, traces.events())
        state = self.load_state(run)
        state.pending_change_set_id = None
        state.pending_change_count = 0
        state.review_status = ReviewStatus.APPLIED
        return run_repo.update_run(db, run, status=RunStatus.COMPLETED.value, pending_change_count=0, review_status=ReviewStatus.APPLIED.value, apply_summary=result["summary"], final_output=((run.final_output or "").strip() + f"\n\n{result['summary']}").strip(), execution_state=state.model_dump(mode="json"))

    def reject_pending_changes(self, db: DBSession, run_id: int) -> Run | None:
        run = run_repo.get_run(db, run_id)
        if run is None:
            return None
        if run.status != RunStatus.WAITING_FOR_REVIEW.value:
            raise ChangeReviewError("Run is not waiting for review")
        change_set = self.change_review_service.get_pending_change_set(db, run.id)
        if change_set is None:
            raise ChangeReviewError("No pending change set is available")

        result = self.change_review_service.reject_change_set(db, change_set)
        traces = TraceCollector()
        traces.record_simple(run.id, EventType.CHANGE_REJECTED, {"change_set_id": change_set.id, **result})
        traces.record_simple(run.id, EventType.RUN_COMPLETED, {"status": RunStatus.COMPLETED.value, "output": result["summary"]})
        self.persist_trace_events(db, run.id, traces.events())
        state = self.load_state(run)
        state.pending_change_set_id = None
        state.pending_change_count = 0
        state.review_status = ReviewStatus.REJECTED
        return run_repo.update_run(db, run, status=RunStatus.COMPLETED.value, pending_change_count=0, review_status=ReviewStatus.REJECTED.value, reject_summary=result["summary"], final_output=((run.final_output or "").strip() + f"\n\n{result['summary']}").strip(), execution_state=state.model_dump(mode="json"))

    def list_changes(self, db: DBSession, run_id: int) -> list[dict[str, Any]]:
        return self.change_review_service.summarize_change_sets(db, run_id)

    def _finalize_review_pending_run(self, db: DBSession, run: Run, state: ExecutionState, final_result) -> Run:
        synthesis_output, synthesis_meta = self.synthesis_engine.synthesize(task=run.task, provider=run.provider, model=run.model, plan=final_result.plan, step_results=final_result.step_results, execution_summary=final_result.execution_summary, evidence=final_result.evidence)
        summary = f"Pending review for {state.pending_change_count} file change(s)."
        return run_repo.update_run(db, run, status=RunStatus.WAITING_FOR_REVIEW.value, pending_change_count=state.pending_change_count, review_status=ReviewStatus.PENDING.value, final_output=f"{synthesis_output}\n\n{summary}".strip(), synthesis_mode=synthesis_meta.mode, synthesis_status=synthesis_meta.status, synthesis_error_summary=synthesis_meta.error_summary, execution_summary=final_result.execution_summary, evidence_summary={"items": len(final_result.evidence.items), "notes": len(final_result.evidence.notes)}, planning_source=final_result.planning_source.value, planning_summary=final_result.planning_summary, fallback_reason=final_result.fallback_reason, budget_config=final_result.budget_config, budget_usage_summary=final_result.budget_usage_summary, execution_state=state.model_dump(mode="json"))

    def _finalize_completed_run(self, db: DBSession, run: Run, state: ExecutionState, final_result) -> Run:
        traces = TraceCollector()
        traces.record_simple(run.id, EventType.SYNTHESIS_STARTED, {"provider": run.provider, "model": run.model, "evidence_items": len(final_result.evidence.items)})
        synthesis_output, synthesis_meta = self.synthesis_engine.synthesize(task=run.task, provider=run.provider, model=run.model, plan=final_result.plan, step_results=final_result.step_results, execution_summary=final_result.execution_summary, evidence=final_result.evidence)
        if synthesis_meta.mode == "deterministic_fallback" and synthesis_meta.error_summary:
            traces.record_simple(run.id, EventType.SYNTHESIS_FAILED, {"provider": run.provider, "model": run.model, "error": synthesis_meta.error_summary, "fallback_mode": synthesis_meta.mode})
        traces.record_simple(run.id, EventType.SYNTHESIS_COMPLETED, {"mode": synthesis_meta.mode, "status": synthesis_meta.status, "provider": synthesis_meta.provider, "provider_status": synthesis_meta.provider_status, "model": synthesis_meta.model, "usage": synthesis_meta.provider_usage_summary, "execution_summary": final_result.execution_summary, "evidence_summary": {"items": len(final_result.evidence.items), "notes": len(final_result.evidence.notes)}})
        terminal_event = EventType.RUN_COMPLETED if final_result.status == RunStatus.COMPLETED else EventType.RUN_FAILED
        traces.record_simple(run.id, terminal_event, {"status": final_result.status.value, "output": synthesis_output})
        self.persist_trace_events(db, run.id, traces.events())
        return run_repo.update_run(db, run, status=final_result.status.value, cancel_requested=False, final_output=synthesis_output, synthesis_mode=synthesis_meta.mode, synthesis_status=synthesis_meta.status, synthesis_error_summary=synthesis_meta.error_summary, execution_summary=final_result.execution_summary, evidence_summary={"items": len(final_result.evidence.items), "notes": len(final_result.evidence.notes)}, planning_source=final_result.planning_source.value, planning_summary=final_result.planning_summary, fallback_reason=final_result.fallback_reason, budget_config=final_result.budget_config, budget_usage_summary=final_result.budget_usage_summary, execution_state=state.model_dump(mode="json"))

    def _finalize_cancelled(self, db: DBSession, run: Run, state: ExecutionState, summary: str) -> Run:
        traces = TraceCollector()
        traces.record_simple(run.id, EventType.RUN_CANCELLED, {"status": RunStatus.CANCELLED.value, "summary": summary})
        self.persist_trace_events(db, run.id, traces.events())
        return run_repo.update_run(db, run, status=RunStatus.CANCELLED.value, cancel_requested=False, final_output=summary, evidence_summary={"items": len(state.evidence.items), "notes": len(state.evidence.notes)}, budget_usage_summary=state.budget_usage_summary, execution_state=state.model_dump(mode="json"))

    @staticmethod
    def serialize_run(db: DBSession, run: Run) -> dict[str, Any]:
        pending_approval = approval_repo.get_latest_pending_approval(db, run.id)
        return {"id": run.id, "session_id": run.session_id, "task": run.task, "provider": run.provider, "model": run.model, "execution_mode": run.execution_mode, "mutation_apply_mode": run.mutation_apply_mode, "planning_source": run.planning_source, "planning_summary": run.planning_summary, "fallback_reason": run.fallback_reason, "status": run.status, "cancel_requested": run.cancel_requested, "pending_change_count": run.pending_change_count, "review_status": run.review_status, "apply_summary": run.apply_summary, "reject_summary": run.reject_summary, "final_output": run.final_output, "synthesis_mode": run.synthesis_mode, "synthesis_status": run.synthesis_status, "synthesis_error_summary": run.synthesis_error_summary, "execution_summary": run.execution_summary, "evidence_summary": run.evidence_summary, "budget_config": run.budget_config, "budget_usage_summary": run.budget_usage_summary, "created_at": run.created_at, "updated_at": run.updated_at, "pending_approval": self_serialize_approval(pending_approval) if pending_approval is not None else None}

    @staticmethod
    def _should_capture_review_first(run: Run, skill: Any | None) -> bool:
        if skill is None or run.mutation_apply_mode != MutationApplyMode.REVIEW_FIRST.value:
            return False
        capabilities = getattr(getattr(skill, "manifest", None), "capabilities", []) or []
        return any(not item.read_only for item in capabilities)

    @staticmethod
    def _check_budget(state: ExecutionState, skill_name: str) -> str | None:
        usage = state.budget_usage_summary or {}
        tool_invocations = int(usage.get("tool_invocations", 0))
        per_skill = dict(usage.get("per_skill", {}))
        if tool_invocations >= state.budget.max_tool_invocations:
            return f"Tool invocation budget reached ({state.budget.max_tool_invocations})"
        if per_skill.get(skill_name, 0) >= state.budget.max_tool_calls_per_skill:
            return f"Per-skill budget reached for {skill_name} ({state.budget.max_tool_calls_per_skill})"
        return None

    @staticmethod
    def _record_budget_usage(state: ExecutionState, skill_name: str) -> None:
        usage = dict(state.budget_usage_summary or {})
        usage["tool_invocations"] = int(usage.get("tool_invocations", 0)) + 1
        per_skill = dict(usage.get("per_skill", {}))
        per_skill[skill_name] = int(per_skill.get(skill_name, 0)) + 1
        usage["per_skill"] = per_skill
        usage.setdefault("fetched_sources", 0)
        usage.setdefault("browser_uses", 0)
        usage.setdefault("shell_uses", 0)
        usage.setdefault("budget_blocked", [])
        state.budget_usage_summary = usage


def self_serialize_approval(approval: ApprovalRequest) -> dict[str, Any]:
    return {"id": approval.id, "run_id": approval.run_id, "step_id": approval.step_id, "reason": approval.reason, "status": approval.status, "resolution_summary": approval.resolution_summary, "created_at": approval.created_at, "updated_at": approval.updated_at}



