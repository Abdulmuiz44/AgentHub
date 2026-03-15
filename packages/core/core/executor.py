from .contracts import (
    EventType,
    PlanStep,
    RunContext,
    RunExecutionResult,
    RunStatus,
    StepExecutionResult,
)
from .tracing import TraceCollector
from skills.base import SkillRequest
from skills.registry import SkillRegistry


class Executor:
    """Synchronous executor for deterministic plan steps."""

    def __init__(self, skill_registry: SkillRegistry) -> None:
        self.skill_registry = skill_registry

    def execute(self, context: RunContext, steps: list[PlanStep], trace_collector: TraceCollector) -> RunExecutionResult:
        step_results: list[StepExecutionResult] = []
        for step in steps:
            if not step.skill_name:
                step_results.append(
                    StepExecutionResult(
                        step_id=step.id,
                        success=False,
                        summary=step.title,
                        error="No executable skill for this step",
                    )
                )
                continue

            trace_collector.record_simple(
                context.run_id,
                EventType.TOOL_REQUESTED,
                {"step_id": step.id, "skill": step.skill_name, "input": step.skill_input},
            )
            trace_collector.record_simple(context.run_id, EventType.TOOL_STARTED, {"step_id": step.id, "skill": step.skill_name})

            skill = self.skill_registry.get_skill(step.skill_name)
            if skill is None:
                error = f"Skill not registered: {step.skill_name}"
                step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=error, error=error))
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_FAILED,
                    {"step_id": step.id, "skill": step.skill_name, "error": error},
                )
                continue

            result = skill.execute(SkillRequest(operation=step.skill_input.get("operation"), input=step.skill_input))
            if result.success:
                step_results.append(
                    StepExecutionResult(
                        step_id=step.id,
                        success=True,
                        summary=result.summary,
                        output=result.output,
                    )
                )
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_COMPLETED,
                    {"step_id": step.id, "skill": step.skill_name, "summary": result.summary, "output": self._summarize_output(result.output)},
                )
            else:
                step_results.append(
                    StepExecutionResult(
                        step_id=step.id,
                        success=False,
                        summary=result.error or "Tool failed",
                        error=result.error,
                    )
                )
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_FAILED,
                    {"step_id": step.id, "skill": step.skill_name, "error": result.error},
                )

        failures = [item for item in step_results if not item.success]
        status = RunStatus.FAILED if failures else RunStatus.COMPLETED
        output = self._build_final_output(step_results)
        return RunExecutionResult(status=status, output=output, plan=steps, step_results=step_results)

    @staticmethod
    def _build_final_output(step_results: list[StepExecutionResult]) -> str:
        if not step_results:
            return "No steps were executed."
        lines = []
        for result in step_results:
            marker = "✓" if result.success else "✗"
            lines.append(f"{marker} {result.step_id}: {result.summary}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_output(output: dict) -> dict:
        summary: dict = {}
        for key, value in output.items():
            if isinstance(value, str):
                summary[key] = value[:300]
            elif isinstance(value, list):
                summary[key] = value[:20]
            else:
                summary[key] = value
        return summary
