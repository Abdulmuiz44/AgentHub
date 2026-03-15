from .contracts import AgentRequest, RunContext, RunStatus
from .executor import Executor
from .planner import Planner


class TaskRunner:
    def __init__(self, planner: Planner | None = None, executor: Executor | None = None):
        self.planner = planner or Planner()
        self.executor = executor or Executor()

    def run(self, request: AgentRequest, context: RunContext) -> RunStatus:
        _ = context
        plan = self.planner.create_plan(request)
        return self.executor.execute(plan)
