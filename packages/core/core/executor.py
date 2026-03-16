from __future__ import annotations

from .contracts import (
    EvidenceBundle,
    EvidenceItem,
    EventType,
    ExecutionBudget,
    ExecutionMode,
    ExecutionState,
    PlanStep,
    PlanningSource,
    RunContext,
    RunExecutionResult,
    RunStatus,
    StepExecutionResult,
)
from .tracing import TraceCollector
from skills.base import SkillRequest
from skills.registry import SkillRegistry


class Executor:
    """Synchronous bounded executor shared by deterministic and model-assisted plans."""

    def __init__(self, skill_registry: SkillRegistry) -> None:
        self.skill_registry = skill_registry

    def execute(
        self,
        context: RunContext,
        steps: list[PlanStep],
        trace_collector: TraceCollector,
        *,
        budget: ExecutionBudget,
        execution_mode: ExecutionMode,
        planning_source: PlanningSource,
        planning_summary: str,
        fallback_reason: str | None,
    ) -> RunExecutionResult:
        state = self.execute_steps(
            context=context,
            steps=steps,
            trace_collector=trace_collector,
            budget=budget,
            checkpoint=ExecutionState(plan=steps, budget=budget),
        )
        return self.build_result(
            state,
            execution_mode=execution_mode,
            planning_source=planning_source,
            planning_summary=planning_summary,
            fallback_reason=fallback_reason,
        )

    def execute_steps(
        self,
        *,
        context: RunContext,
        steps: list[PlanStep],
        trace_collector: TraceCollector,
        budget: ExecutionBudget,
        checkpoint: ExecutionState,
        max_steps: int | None = None,
    ) -> ExecutionState:
        state = checkpoint.model_copy(deep=True)
        state.plan = list(steps)
        state.budget = budget
        usage = self._hydrate_usage(state.budget_usage_summary)
        executed = 0

        while state.current_step_index < len(steps):
            step = steps[state.current_step_index]
            if max_steps is not None and executed >= max_steps:
                break
            if not step.skill_name:
                state.step_results.append(
                    StepExecutionResult(step_id=step.id, success=False, summary=step.title, error="No executable skill for this step")
                )
                state.current_step_index += 1
                executed += 1
                continue

            dynamic_input = dict(step.skill_input)
            if step.skill_name == "fetch" and step.skill_input.get("from_search"):
                remaining_fetches = max(0, budget.max_fetched_sources - usage["fetched_sources"])
                max_urls = min(int(step.skill_input.get("max_urls", 2)), remaining_fetches)
                selected = state.working_search_results[: max(0, max_urls)]
                dynamic_input["urls"] = [item["url"] for item in selected]

            skill = self.skill_registry.get_skill(step.skill_name)
            runtime_type = skill.manifest.runtime_type.value if skill is not None else "unknown"
            skill_metadata = self._skill_runtime_metadata(skill)
            trace_collector.record_simple(
                context.run_id,
                EventType.TOOL_REQUESTED,
                {
                    "step_id": step.id,
                    "skill": step.skill_name,
                    "runtime_type": runtime_type,
                    "is_builtin": skill_metadata.get("builtin", False),
                    "selection_reason": step.selection_reason,
                    "decision_summary": step.decision_summary,
                    "config_readiness": skill_metadata.get("config_readiness"),
                    "resolved_env_keys": skill_metadata.get("resolved_env_keys", []),
                    "input": self._summarize_output(dynamic_input),
                },
            )

            budget_error = self._check_step_budget(step.skill_name, skill_metadata, budget, usage)
            if budget_error is not None:
                usage["budget_blocked"].append(budget_error)
                trace_collector.record_simple(
                    context.run_id,
                    EventType.BUDGET_ENFORCED,
                    {
                        "step_id": step.id,
                        "skill": step.skill_name,
                        "reason": budget_error,
                        "usage": self._budget_usage_summary(usage),
                    },
                )
                state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=budget_error, error=budget_error))
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_FAILED,
                    {
                        "step_id": step.id,
                        "skill": step.skill_name,
                        "runtime_type": runtime_type,
                        "is_builtin": skill_metadata.get("builtin", False),
                        "error": budget_error,
                    },
                )
                state.current_step_index += 1
                executed += 1
                continue

            trace_collector.record_simple(
                context.run_id,
                EventType.TOOL_STARTED,
                {
                    "step_id": step.id,
                    "skill": step.skill_name,
                    "runtime_type": runtime_type,
                    "is_builtin": skill_metadata.get("builtin", False),
                    "config_readiness": skill_metadata.get("config_readiness"),
                },
            )

            if step.skill_name == "fetch" and dynamic_input.get("from_search"):
                fetch_result = self._execute_fetch_from_search(
                    step_id=step.id,
                    urls=dynamic_input.get("urls", []),
                    budget=budget,
                    usage=usage,
                    trace_collector=trace_collector,
                    context=context,
                )
                state.step_results.append(fetch_result)
                if fetch_result.success:
                    self._collect_fetch_evidence(state.evidence, fetch_result.output)
                    trace_collector.record_simple(
                        context.run_id,
                        EventType.TOOL_COMPLETED,
                        {
                            "step_id": step.id,
                            "skill": step.skill_name,
                            "runtime_type": "native_python",
                            "is_builtin": True,
                            "summary": fetch_result.summary,
                            "output": self._summarize_output(fetch_result.output),
                        },
                    )
                else:
                    trace_collector.record_simple(
                        context.run_id,
                        EventType.TOOL_FAILED,
                        {
                            "step_id": step.id,
                            "skill": step.skill_name,
                            "runtime_type": "native_python",
                            "is_builtin": True,
                            "error": fetch_result.error,
                        },
                    )
                state.current_step_index += 1
                executed += 1
                continue

            if skill is None:
                error = f"Skill not registered: {step.skill_name}"
                state.step_results.append(StepExecutionResult(step_id=step.id, success=False, summary=error, error=error))
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_FAILED,
                    {"step_id": step.id, "skill": step.skill_name, "runtime_type": runtime_type, "is_builtin": False, "error": error},
                )
                state.current_step_index += 1
                executed += 1
                continue

            self._record_tool_usage(step.skill_name, usage)
            result = skill.execute(SkillRequest(operation=dynamic_input.get("operation"), input=dynamic_input))
            if result.success:
                step_result = StepExecutionResult(step_id=step.id, success=True, summary=result.summary, output=result.output)
                state.step_results.append(step_result)
                self._collect_evidence(step.skill_name, result.output, state.evidence)
                if step.skill_name == "web_search":
                    state.working_search_results = list(result.output.get("results", []))
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_COMPLETED,
                    {
                        "step_id": step.id,
                        "skill": step.skill_name,
                        "runtime_type": result.runtime_type.value,
                        "is_builtin": result.metadata.get("builtin", False),
                        "config_readiness": result.metadata.get("config_readiness"),
                        "resolved_env_keys": result.metadata.get("resolved_env_keys", []),
                        "summary": result.summary,
                        "metadata": self._summarize_output(result.metadata),
                        "output": self._summarize_output(result.output),
                    },
                )
            else:
                state.step_results.append(
                    StepExecutionResult(step_id=step.id, success=False, summary=result.error or "Tool failed", error=result.error)
                )
                trace_collector.record_simple(
                    context.run_id,
                    EventType.TOOL_FAILED,
                    {
                        "step_id": step.id,
                        "skill": step.skill_name,
                        "runtime_type": result.runtime_type.value,
                        "is_builtin": result.metadata.get("builtin", False),
                        "config_readiness": result.metadata.get("config_readiness"),
                        "resolved_env_keys": result.metadata.get("resolved_env_keys", []),
                        "metadata": self._summarize_output(result.metadata),
                        "error": result.error,
                    },
                )

            state.current_step_index += 1
            executed += 1

        state.budget_usage_summary = self._budget_usage_summary(usage)
        return state

    def build_result(
        self,
        state: ExecutionState,
        *,
        execution_mode: ExecutionMode,
        planning_source: PlanningSource,
        planning_summary: str,
        fallback_reason: str | None,
    ) -> RunExecutionResult:
        hard_failures = [item for item in state.step_results if not item.success and item.step_id != "search-fetch"]
        status = RunStatus.FAILED if hard_failures and not state.evidence.items else RunStatus.COMPLETED
        execution_summary = self._build_execution_summary(step_results=state.step_results, evidence=state.evidence)
        output = self._build_final_output(state.step_results)
        return RunExecutionResult(
            status=status,
            output=output,
            plan=state.plan,
            step_results=state.step_results,
            execution_summary=execution_summary,
            evidence=state.evidence,
            execution_mode=execution_mode,
            planning_source=planning_source,
            planning_summary=planning_summary,
            fallback_reason=fallback_reason,
            budget_config=state.budget.model_dump(mode="json"),
            budget_usage_summary=state.budget_usage_summary,
        )

    def _execute_fetch_from_search(
        self,
        *,
        step_id: str,
        urls: list[str],
        budget: ExecutionBudget,
        usage: dict,
        trace_collector: TraceCollector,
        context: RunContext,
    ) -> StepExecutionResult:
        fetch_skill = self.skill_registry.get_skill("fetch")
        if fetch_skill is None:
            return StepExecutionResult(step_id=step_id, success=False, summary="Fetch skill is not available", error="fetch_unavailable")

        fetched: list[dict] = []
        errors: list[str] = []
        for url in urls:
            if usage["fetched_sources"] >= budget.max_fetched_sources:
                reason = f"Fetch source budget reached ({budget.max_fetched_sources})"
                usage["budget_blocked"].append(reason)
                trace_collector.record_simple(
                    context.run_id,
                    EventType.BUDGET_ENFORCED,
                    {"step_id": step_id, "skill": "fetch", "reason": reason, "usage": self._budget_usage_summary(usage)},
                )
                break
            budget_error = self._check_step_budget("fetch", {"capability_categories": ["web_fetch"]}, budget, usage)
            if budget_error is not None:
                usage["budget_blocked"].append(budget_error)
                trace_collector.record_simple(
                    context.run_id,
                    EventType.BUDGET_ENFORCED,
                    {"step_id": step_id, "skill": "fetch", "reason": budget_error, "usage": self._budget_usage_summary(usage)},
                )
                errors.append(budget_error)
                break
            self._record_tool_usage("fetch", usage)
            usage["fetched_sources"] += 1
            result = fetch_skill.execute(SkillRequest(input={"url": url}))
            if result.success:
                metadata = dict(result.output.get("metadata", {}))
                text = str(result.output.get("text", ""))
                fetched.append({
                    "url": metadata.get("url", url),
                    "status_code": metadata.get("status_code"),
                    "content_type": metadata.get("content_type"),
                    "summary": self._snippet(text),
                })
            else:
                errors.append(f"{url}: {result.error or 'fetch failed'}")

        success = bool(fetched)
        summary = f"Fetched {len(fetched)}/{len(urls)} search result pages"
        output = {"fetched_pages": fetched, "errors": errors, "requested_urls": urls}
        return StepExecutionResult(step_id=step_id, success=success, summary=summary, output=output, error="; ".join(errors) if errors else None)

    def _collect_evidence(self, skill_name: str, output: dict, evidence: EvidenceBundle) -> None:
        if skill_name == "web_search":
            query = str(output.get("query", ""))
            for item in output.get("results", []):
                evidence.items.append(
                    EvidenceItem(
                        source_type="search_result",
                        source_ref=str(item.get("url", "")),
                        title=str(item.get("title", "")).strip() or None,
                        excerpt=str(item.get("snippet", "")).strip(),
                        metadata={"rank": item.get("rank"), "query": query},
                    )
                )
        elif skill_name == "filesystem":
            content = str(output.get("content", ""))
            path = str(output.get("path", ""))
            evidence.items.append(
                EvidenceItem(source_type="filesystem", source_ref=path, title=path, excerpt=self._snippet(content), metadata={"chars": output.get("chars")})
            )
        elif output.get("text"):
            evidence.items.append(
                EvidenceItem(
                    source_type="skill_output",
                    source_ref=skill_name,
                    title=skill_name,
                    excerpt=self._snippet(str(output.get("text", ""))),
                    metadata={"runtime": output.get("runtime_type")},
                )
            )

    def _collect_fetch_evidence(self, evidence: EvidenceBundle, output: dict) -> None:
        for page in output.get("fetched_pages", []):
            evidence.items.append(
                EvidenceItem(
                    source_type="web_page",
                    source_ref=str(page.get("url", "")),
                    title=str(page.get("url", "")),
                    excerpt=str(page.get("summary", "")),
                    metadata={"status_code": page.get("status_code")},
                )
            )
        for error in output.get("errors", []):
            evidence.notes.append(str(error))

    @staticmethod
    def _check_step_budget(skill_name: str, skill_metadata: dict, budget: ExecutionBudget, usage: dict) -> str | None:
        if usage["tool_invocations"] >= budget.max_tool_invocations:
            return f"Tool invocation budget reached ({budget.max_tool_invocations})"
        if usage["per_skill"].get(skill_name, 0) >= budget.max_tool_calls_per_skill:
            return f"Per-skill budget reached for {skill_name} ({budget.max_tool_calls_per_skill})"
        categories = skill_metadata.get("capability_categories", [])
        if "rendered_browse" in categories and usage["browser_uses"] >= budget.max_browser_uses:
            return f"Browser usage budget reached ({budget.max_browser_uses})"
        if "shell_verify" in categories and usage["shell_uses"] >= budget.max_shell_uses:
            return f"Shell usage budget reached ({budget.max_shell_uses})"
        return None

    @staticmethod
    def _record_tool_usage(skill_name: str, usage: dict) -> None:
        usage["tool_invocations"] += 1
        usage["per_skill"][skill_name] = usage["per_skill"].get(skill_name, 0) + 1

    @staticmethod
    def _hydrate_usage(summary: dict | None) -> dict:
        summary = summary or {}
        return {
            "tool_invocations": int(summary.get("tool_invocations", 0)),
            "per_skill": dict(summary.get("per_skill", {})),
            "fetched_sources": int(summary.get("fetched_sources", 0)),
            "browser_uses": int(summary.get("browser_uses", 0)),
            "shell_uses": int(summary.get("shell_uses", 0)),
            "budget_blocked": list(summary.get("budget_blocked", [])),
        }

    @staticmethod
    def _budget_usage_summary(usage: dict) -> dict:
        return {
            "tool_invocations": usage["tool_invocations"],
            "per_skill": dict(usage["per_skill"]),
            "fetched_sources": usage["fetched_sources"],
            "browser_uses": usage["browser_uses"],
            "shell_uses": usage["shell_uses"],
            "budget_blocked": list(usage["budget_blocked"]),
        }

    @staticmethod
    def _snippet(text: str, limit: int = 500) -> str:
        cleaned = " ".join(text.split())
        return cleaned[:limit]

    @staticmethod
    def _build_execution_summary(*, step_results: list[StepExecutionResult], evidence: EvidenceBundle) -> dict:
        success_count = sum(1 for item in step_results if item.success)
        return {
            "steps_total": len(step_results),
            "steps_success": success_count,
            "steps_failed": len(step_results) - success_count,
            "evidence_items": len(evidence.items),
            "evidence_notes": len(evidence.notes),
        }

    @staticmethod
    def _build_final_output(step_results: list[StepExecutionResult]) -> str:
        if not step_results:
            return "No steps were executed."
        lines = []
        for result in step_results:
            marker = "[ok]" if result.success else "[failed]"
            lines.append(f"{marker} {result.step_id}: {result.summary}")
        return "\n".join(lines)

    @staticmethod
    def _summarize_output(output: dict) -> dict:
        summary: dict = {}
        for key, value in output.items():
            if isinstance(value, str):
                summary[key] = value[:300]
            elif isinstance(value, list):
                summary[key] = value[:10]
            else:
                summary[key] = value
        return summary

    @staticmethod
    def _skill_runtime_metadata(skill: object | None) -> dict:
        if skill is None:
            return {}
        if hasattr(skill, "runtime_metadata") and isinstance(getattr(skill, "runtime_metadata"), dict):
            return dict(getattr(skill, "runtime_metadata"))
        if hasattr(skill, "readiness_status"):
            readiness = getattr(skill, "readiness_status")
            return {
                "config_readiness": getattr(readiness, "value", readiness),
                "builtin": bool(getattr(skill, "is_builtin", False)),
                "capability_categories": [item.value for item in getattr(getattr(skill, "manifest", None), "capability_categories", [])],
            }
        return {"builtin": bool(getattr(skill, "is_builtin", False))}
