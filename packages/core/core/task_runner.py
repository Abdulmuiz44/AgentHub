from .contracts import AgentRequest, EventType, RunContext, RunExecutionResult
from .executor import Executor
from .planner import Planner
from .synthesis import SynthesisEngine
from .tracing import TraceCollector


class TaskRunner:
    def __init__(self, planner: Planner, executor: Executor, synthesis_engine: SynthesisEngine | None = None):
        self.planner = planner
        self.executor = executor
        self.synthesis_engine = synthesis_engine or SynthesisEngine()

    def run(self, request: AgentRequest, context: RunContext) -> tuple[RunExecutionResult, list]:
        traces = TraceCollector()
        traces.record_simple(context.run_id, EventType.RUN_STARTED, {"status": "running", "context": context.model_dump(mode="json")})

        plan = self.planner.create_plan(request)
        traces.record_simple(
            context.run_id,
            EventType.PLAN_CREATED,
            {"plan": [item.model_dump(mode="json") for item in plan], "requested_skills": request.enabled_skills},
        )

        result = self.executor.execute(context=context, steps=plan, trace_collector=traces)

        traces.record_simple(
            context.run_id,
            EventType.SYNTHESIS_STARTED,
            {"provider": request.provider, "model": request.model},
        )

        synthesis_output, synthesis_meta = self.synthesis_engine.synthesize(
            task=request.task,
            provider=request.provider,
            model=request.model,
            plan=result.plan,
            step_results=result.step_results,
            execution_summary=result.output,
        )

        if synthesis_meta.mode == "deterministic_fallback" and synthesis_meta.error_summary:
            traces.record_simple(
                context.run_id,
                EventType.SYNTHESIS_FAILED,
                {
                    "provider": request.provider,
                    "model": request.model,
                    "error": synthesis_meta.error_summary,
                    "fallback_mode": synthesis_meta.mode,
                },
            )

        traces.record_simple(
            context.run_id,
            EventType.SYNTHESIS_COMPLETED,
            {
                "mode": synthesis_meta.mode,
                "status": synthesis_meta.status,
                "provider": synthesis_meta.provider,
                "provider_status": synthesis_meta.provider_status,
                "model": synthesis_meta.model,
                "usage": synthesis_meta.provider_usage_summary,
            },
        )

        result.output = synthesis_output
        result.synthesis = synthesis_meta

        if result.status.value == "completed":
            traces.record_simple(context.run_id, EventType.RUN_COMPLETED, {"status": result.status.value, "output": result.output})
        else:
            traces.record_simple(context.run_id, EventType.RUN_FAILED, {"status": result.status.value, "output": result.output})

        return result, traces.events()
