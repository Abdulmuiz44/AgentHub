from .contracts import AgentRequest, EventType, RunContext, RunExecutionResult
from .executor import Executor
from .planner import Planner
from .tracing import TraceCollector


class TaskRunner:
    def __init__(self, planner: Planner, executor: Executor):
        self.planner = planner
        self.executor = executor

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
        return result, traces.events()
