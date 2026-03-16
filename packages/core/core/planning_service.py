from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from models.base import ProviderGenerationRequest, ProviderGenerationSettings, ProviderMessage
from models.registry import ProviderRegistry

from .contracts import AgentRequest, ExecutionMode, PlanStep, PlanningSource
from .planner import Planner


@dataclass
class PlanningOutcome:
    plan: list[PlanStep]
    planning_source: PlanningSource
    planning_summary: str
    fallback_reason: str | None = None
    validation_error: str | None = None


class PlanningService:
    def __init__(self, planner: Planner | None = None, provider_registry: ProviderRegistry | None = None) -> None:
        self.planner = planner or Planner()
        self.provider_registry = provider_registry or ProviderRegistry.default()

    def create_plan(self, request: AgentRequest) -> PlanningOutcome:
        deterministic_plan = self.planner.create_plan(request)
        deterministic_summary = self._summarize_plan_source(PlanningSource.DETERMINISTIC, deterministic_plan)
        if request.execution_mode == ExecutionMode.DETERMINISTIC:
            return PlanningOutcome(
                plan=deterministic_plan,
                planning_source=PlanningSource.DETERMINISTIC,
                planning_summary=deterministic_summary,
            )

        planning_error = self._planning_unavailable_reason(request)
        if planning_error:
            return PlanningOutcome(
                plan=deterministic_plan,
                planning_source=PlanningSource.FALLBACK,
                planning_summary=deterministic_summary,
                fallback_reason=planning_error,
            )

        provider_plan = self._request_provider_plan(request)
        if provider_plan is None:
            return PlanningOutcome(
                plan=deterministic_plan,
                planning_source=PlanningSource.FALLBACK,
                planning_summary=deterministic_summary,
                fallback_reason="Provider planning returned no usable structured output",
            )

        validation_error = self._validate_provider_plan(provider_plan, request)
        if validation_error is not None:
            return PlanningOutcome(
                plan=deterministic_plan,
                planning_source=PlanningSource.FALLBACK,
                planning_summary=deterministic_summary,
                fallback_reason=validation_error,
                validation_error=validation_error,
            )

        return PlanningOutcome(
            plan=provider_plan,
            planning_source=PlanningSource.PROVIDER,
            planning_summary=self._summarize_plan_source(PlanningSource.PROVIDER, provider_plan),
        )

    def _planning_unavailable_reason(self, request: AgentRequest) -> str | None:
        if not request.planning_skills:
            return "No enabled ready skills with planning metadata were available"
        if not request.provider or request.provider == "builtin" or not request.model or request.model == "deterministic":
            return "Model-assisted planning requires a configured provider and non-deterministic model"
        adapter = self.provider_registry.get(request.provider)
        if adapter is None:
            return f"Planning provider is unavailable: {request.provider}"
        return None

    def _request_provider_plan(self, request: AgentRequest) -> list[PlanStep] | None:
        adapter = self.provider_registry.get(request.provider)
        if adapter is None:
            return None
        prompt = self._build_planning_prompt(request)
        response = adapter.generate(
            ProviderGenerationRequest(
                model=request.model,
                messages=[
                    ProviderMessage(
                        role="system",
                        content=(
                            "Return only compact JSON for a bounded tool plan. Do not include reasoning, markdown, or commentary. "
                            "Use only the provided skills and stay within the stated budgets."
                        ),
                    ),
                    ProviderMessage(role="user", content=prompt),
                ],
                settings=ProviderGenerationSettings(temperature=0.1, max_tokens=700),
                metadata={"purpose": "planning", "execution_mode": request.execution_mode.value},
            )
        )
        if response.error is not None or not response.output_text:
            return None
        return self._parse_provider_plan(response.output_text)

    def _build_planning_prompt(self, request: AgentRequest) -> str:
        planning_skills = [
            {
                "name": item.name,
                "runtime_type": item.runtime_type,
                "description": item.description,
                "scopes": item.scopes,
                "capability_categories": item.capability_categories,
            }
            for item in request.planning_skills
        ]
        payload = {
            "task": request.task,
            "budget": request.budget.model_dump(mode="json"),
            "available_skills": planning_skills,
            "output_schema": {
                "decision_summary": "short explanation of the overall plan choice",
                "steps": [
                    {
                        "title": "short step title",
                        "skill_name": "must match an available skill",
                        "skill_input": {"key": "value"},
                        "decision_summary": "short safe reason for choosing the step",
                    }
                ],
            },
        }
        return json.dumps(payload)

    def _parse_provider_plan(self, text: str) -> list[PlanStep] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        steps_payload = payload.get("steps")
        overall_summary = str(payload.get("decision_summary", "")).strip()
        if not isinstance(steps_payload, list) or not steps_payload:
            return None

        plan: list[PlanStep] = []
        for index, item in enumerate(steps_payload, start=1):
            if not isinstance(item, dict):
                return None
            skill_input = item.get("skill_input", {})
            if not isinstance(skill_input, dict):
                return None
            plan.append(
                PlanStep(
                    id=f"step-{index}",
                    title=str(item.get("title") or f"Execute step {index}"),
                    skill_name=str(item.get("skill_name") or "").strip() or None,
                    skill_input=skill_input,
                    selection_reason="model_assisted",
                    decision_summary=str(item.get("decision_summary") or overall_summary or "Model-assisted planner selected this step.")[:220],
                )
            )
        return plan

    def _validate_provider_plan(self, plan: list[PlanStep], request: AgentRequest) -> str | None:
        if len(plan) > request.budget.max_plan_steps:
            return f"Provider plan exceeded max plan steps ({request.budget.max_plan_steps})"

        descriptors = {item.name: item for item in request.planning_skills}
        for step in plan:
            if not step.skill_name or step.skill_name not in descriptors:
                return f"Provider selected unknown skill: {step.skill_name or 'missing'}"
            descriptor = descriptors[step.skill_name]
            if descriptor.readiness != "ready":
                return f"Provider selected not-ready skill: {step.skill_name}"
            if descriptor.approval_required:
                return f"Provider selected approval-gated skill: {step.skill_name}"
            if not descriptor.capability_categories:
                return f"Provider selected skill without capability metadata: {step.skill_name}"
            if not isinstance(step.skill_input, dict):
                return f"Provider emitted malformed input for {step.skill_name}"
            safe_error = self._validate_step_input(step.skill_name, step.skill_input)
            if safe_error:
                return safe_error
        return None

    @staticmethod
    def _validate_step_input(skill_name: str, skill_input: dict[str, Any]) -> str | None:
        if skill_name == "filesystem":
            allowed_keys = {"operation", "path"}
            if not set(skill_input).issubset(allowed_keys):
                return "Provider emitted unsupported filesystem inputs"
            if skill_input.get("operation") not in {"list_directory", "read_text_file"}:
                return "Provider emitted unsupported filesystem operation"
        elif skill_name == "fetch":
            allowed_keys = {"url", "source", "from_search", "max_urls"}
            if not set(skill_input).issubset(allowed_keys):
                return "Provider emitted unsupported fetch inputs"
        elif skill_name == "web_search":
            allowed_keys = {"query", "max_results", "timeout_seconds"}
            if not set(skill_input).issubset(allowed_keys):
                return "Provider emitted unsupported web_search inputs"
        for value in skill_input.values():
            if isinstance(value, (dict, set, tuple)):
                return f"Provider emitted unsupported nested input for {skill_name}"
        return None

    @staticmethod
    def _summarize_plan_source(source: PlanningSource, plan: list[PlanStep]) -> str:
        skill_names = [step.skill_name for step in plan if step.skill_name]
        if not skill_names:
            return f"{source.value} planning produced no executable steps"
        unique_skills = ", ".join(dict.fromkeys(skill_names))
        return f"{source.value} planning selected {len(plan)} step(s) using: {unique_skills}"
