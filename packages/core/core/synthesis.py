from __future__ import annotations

from .contracts import PlanStep, StepExecutionResult, SynthesisMetadata
from models.base import ProviderGenerationRequest, ProviderMessage
from models.registry import ProviderRegistry


class SynthesisEngine:
    def __init__(self, provider_registry: ProviderRegistry | None = None) -> None:
        self.provider_registry = provider_registry or ProviderRegistry.default()

    def synthesize(
        self,
        *,
        task: str,
        provider: str,
        model: str,
        plan: list[PlanStep],
        step_results: list[StepExecutionResult],
        execution_summary: str,
    ) -> tuple[str, SynthesisMetadata]:
        if not provider or not model or provider == "builtin" or model == "deterministic":
            return self._fallback_output(
                task=task,
                provider=provider,
                model=model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary="Model provider configuration missing or deterministic mode selected",
            )

        adapter = self.provider_registry.get(provider)
        if adapter is None:
            return self._fallback_output(
                task=task,
                provider=provider,
                model=model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary=f"Provider not found: {provider}",
            )

        try:
            prompt = self._build_prompt(task=task, plan=plan, step_results=step_results, execution_summary=execution_summary)
            response = adapter.generate(
                ProviderGenerationRequest(
                    model=model,
                    messages=[ProviderMessage(role="user", content=prompt)],
                )
            )
            if response.error:
                raise RuntimeError(f"{response.error.code}: {response.error.message}")

            output = response.output_text
            if not output:
                raise RuntimeError("Provider response did not include output_text")

            metadata = SynthesisMetadata(mode="provider", status="completed", provider=provider, model=model)
            return output, metadata
        except Exception as exc:
            return self._fallback_output(
                task=task,
                provider=provider,
                model=model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary=str(exc),
            )

    @staticmethod
    def _build_prompt(
        *,
        task: str,
        plan: list[PlanStep],
        step_results: list[StepExecutionResult],
        execution_summary: str,
    ) -> str:
        plan_lines = [f"- {step.id}: {step.title}" for step in plan]
        result_lines = [
            f"- {result.step_id} ({'success' if result.success else 'failure'}): {result.summary}"
            for result in step_results
        ]
        return "\n".join(
            [
                "Synthesize final run output from deterministic execution.",
                f"Task: {task}",
                "Plan:",
                *plan_lines,
                "Step Results:",
                *result_lines,
                "Execution Summary:",
                execution_summary,
            ]
        )

    def _fallback_output(
        self,
        *,
        task: str,
        provider: str,
        model: str,
        plan: list[PlanStep],
        step_results: list[StepExecutionResult],
        execution_summary: str,
        error_summary: str,
    ) -> tuple[str, SynthesisMetadata]:
        output = self._local_synthesis(task=task, plan=plan, step_results=step_results, execution_summary=execution_summary)
        metadata = SynthesisMetadata(
            mode="deterministic_fallback",
            status="completed",
            provider=provider,
            model=model,
            error_summary=error_summary,
        )
        return output, metadata

    @staticmethod
    def _local_synthesis(
        *,
        task: str,
        plan: list[PlanStep],
        step_results: list[StepExecutionResult],
        execution_summary: str,
    ) -> str:
        completed = sum(1 for item in step_results if item.success)
        total = len(step_results)
        lines = [
            f"Task: {task}",
            f"Completed steps: {completed}/{total}",
            f"Planned steps: {len(plan)}",
            "Execution summary:",
            execution_summary,
        ]
        return "\n".join(lines)
