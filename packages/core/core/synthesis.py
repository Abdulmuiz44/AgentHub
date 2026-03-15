from __future__ import annotations

from .contracts import PlanStep, StepExecutionResult, SynthesisMetadata
from models.base import ProviderGenerationRequest, ProviderGenerationSettings, ProviderMessage, ProviderUsage
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
                status="skipped",
                provider_status="not_requested",
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
                status="failed",
                provider_status="not_available",
            )

        prompt = self._build_prompt(task=task, plan=plan, step_results=step_results, execution_summary=execution_summary)
        request_model = ProviderGenerationRequest(
            model=model,
            messages=[ProviderMessage(role="user", content=self._normalize_text(prompt))],
            settings=self._normalize_settings(ProviderGenerationSettings()),
        )

        try:
            response = adapter.generate(request_model)
        except Exception as exc:
            return self._fallback_output(
                task=task,
                provider=provider,
                model=model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary=f"Unexpected provider exception: {exc}",
                status="failed",
                provider_status="exception",
            )

        response_model = response.model or model
        usage_summary = self._summarize_usage(response.usage)

        if response.error is not None:
            error_summary = f"{response.error.code}: {response.error.message}"
            return self._fallback_output(
                task=task,
                provider=provider,
                model=response_model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary=error_summary,
                status="failed",
                provider_status="error",
                provider_usage_summary=usage_summary,
            )

        output_text = self._normalize_text(response.output_text)
        if not output_text:
            return self._fallback_output(
                task=task,
                provider=provider,
                model=response_model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                error_summary="invalid_response: Provider returned empty output",
                status="failed",
                provider_status="invalid_response",
                provider_usage_summary=usage_summary,
            )

        metadata = SynthesisMetadata(
            mode="provider",
            status="completed",
            provider=response.provider or provider,
            model=response_model,
            provider_status="completed",
            provider_usage_summary=usage_summary,
        )
        return output_text, metadata

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
        status: str,
        provider_status: str,
        provider_usage_summary: str | None = None,
    ) -> tuple[str, SynthesisMetadata]:
        output = self._local_synthesis(task=task, plan=plan, step_results=step_results, execution_summary=execution_summary)
        metadata = SynthesisMetadata(
            mode="deterministic_fallback",
            status=status,
            provider=provider,
            model=model,
            provider_status=provider_status,
            provider_usage_summary=provider_usage_summary,
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

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return value.strip()

    @staticmethod
    def _normalize_settings(settings: ProviderGenerationSettings | None) -> ProviderGenerationSettings:
        if settings is None:
            return ProviderGenerationSettings()
        return ProviderGenerationSettings(
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
            top_p=settings.top_p,
            stream=bool(settings.stream),
            stop=[item for item in settings.stop if item],
        )

    @staticmethod
    def _summarize_usage(usage: ProviderUsage | None) -> str | None:
        if usage is None:
            return None
        if usage.input_tokens is None and usage.output_tokens is None and usage.total_tokens is None:
            return None
        return f"in={usage.input_tokens or 0},out={usage.output_tokens or 0},total={usage.total_tokens or 0}"
