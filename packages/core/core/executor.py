from .contracts import PlanStep, RunStatus


class Executor:
    """Executor skeleton for processing plan steps without LLM orchestration yet."""

    def execute(self, steps: list[PlanStep]) -> RunStatus:
        for _step in steps:
            pass
        return RunStatus.COMPLETED
