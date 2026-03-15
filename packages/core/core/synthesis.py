from __future__ import annotations

from .contracts import EvidenceBundle, PlanStep, StepExecutionResult, SynthesisMetadata
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
        execution_summary: dict,
        evidence: EvidenceBundle,
    ) -> tuple[str, SynthesisMetadata]:
        if not provider or not model or provider == "builtin" or model == "deterministic":
            return self._fallback_output(
                task=task,
                provider=provider,
                model=model,
                plan=plan,
                step_results=step_results,
                execution_summary=execution_summary,
                evidence=evidence,
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
                evidence=evidence,
                error_summary=f"Provider not found: {provider}",
                status="failed",
                provider_status="not_available",
            )

        prompt = self._build_prompt(
            task=task,
            plan=plan,
            step_results=step_results,
            execution_summary=execution_summary,
            evidence=evidence,
        )
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
                evidence=evidence,
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
                evidence=evidence,
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
                evidence=evidence,
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
        execution_summary: dict,
        evidence: EvidenceBundle,
    ) -> str:
        plan_lines = [f"- {step.id}: {step.title}" for step in plan]
        result_lines = [
            f"- {result.step_id} ({'success' if result.success else 'failure'}): {result.summary}"
            for result in step_results
        ]
        evidence_lines = [
            f"- [{item.source_type}] {item.title or item.source_ref}: {item.excerpt[:220]}"
            for item in evidence.items[:10]
        ]
        return "\n".join(
            [
                "Synthesize final run output from deterministic execution.",
                f"Task: {task}",
                "Plan:",
                *plan_lines,
                "Step Results:",
                *result_lines,
                "Evidence:",
                *evidence_lines,
                "Execution Summary:",
                str(execution_summary),
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
        execution_summary: dict,
        evidence: EvidenceBundle,
        error_summary: str,
        status: str,
        provider_status: str,
        provider_usage_summary: str | None = None,
    ) -> tuple[str, SynthesisMetadata]:
        output = self._local_synthesis(
            task=task,
            plan=plan,
            step_results=step_results,
            execution_summary=execution_summary,
            evidence=evidence,
        )
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
        execution_summary: dict,
        evidence: EvidenceBundle,
    ) -> str:
        sources = [item for item in evidence.items if item.source_type in {"web_page", "search_result", "filesystem"}]
        comparisons = len({item.source_ref for item in sources}) > 1
        lines = [
            f"Task: {task}",
            f"Planned steps: {len(plan)}",
            f"Completed steps: {sum(1 for item in step_results if item.success)}/{len(step_results)}",
            "",
            "Summary:",
        ]

        if sources:
            lines.append(
                "Compared evidence across multiple sources." if comparisons else "Collected evidence from available source(s)."
            )
            for item in sources[:6]:
                label = item.title or item.source_ref
                lines.append(f"- {label}: {item.excerpt[:180]}")
        else:
            lines.append("No strong evidence collected. Output may be incomplete.")

        if evidence.notes:
            lines.append("")
            lines.append("Gaps / errors:")
            for note in evidence.notes[:5]:
                lines.append(f"- {note}")

        lines.append("")
        lines.append("Source references:")
        refs = []
        for item in sources[:8]:
            if item.source_ref not in refs:
                refs.append(item.source_ref)
        for idx, ref in enumerate(refs, start=1):
            lines.append(f"[{idx}] {ref}")

        lines.append("")
        lines.append(f"Execution summary: {execution_summary}")
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
