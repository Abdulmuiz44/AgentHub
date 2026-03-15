from .contracts import AgentRequest, PlanStep


class Planner:
    """Planner skeleton for converting requests into stable plan steps."""

    def create_plan(self, request: AgentRequest) -> list[PlanStep]:
        return [PlanStep(id="step-1", title=f"Handle task: {request.task}")]
