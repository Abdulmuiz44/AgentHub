import re

from .contracts import AgentRequest, PlanStep

_URL_RE = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
_FILE_HINT_RE = re.compile(
    r"(?:\./|/|[\w\-]+\.[a-zA-Z0-9]{1,8}|read\s+file|list\s+(?:files|directory|dir)|repo|directory)",
    re.IGNORECASE,
)
_RESEARCH_HINT_RE = re.compile(r"\b(research|find|compare|look\s*up|pricing|documentation|docs)\b", re.IGNORECASE)
_COMPARE_HINT_RE = re.compile(r"\b(compare|versus|vs\.?|difference)\b", re.IGNORECASE)
_EXPLICIT_SKILL_RE = re.compile(r"\buse\s+skill\s+([a-zA-Z0-9_\-]+)\b", re.IGNORECASE)


class Planner:
    """Deterministic planner for alpha research execution and explicit skill routing."""

    def create_plan(self, request: AgentRequest) -> list[PlanStep]:
        task = request.task.strip()
        explicit_skill = self._extract_explicit_skill(task)
        if explicit_skill:
            if request.available_skills and explicit_skill not in request.available_skills:
                return [
                    PlanStep(
                        id="step-1",
                        title=f"Requested skill {explicit_skill} is not installed or enabled",
                        selection_reason="explicit_skill_missing",
                    )
                ]
            if not self._allows_skill(request, explicit_skill):
                return [
                    PlanStep(
                        id="step-1",
                        title=f"Requested skill {explicit_skill} is disabled for this run",
                        selection_reason="explicit_skill_disabled",
                    )
                ]
            return [
                PlanStep(
                    id="step-1",
                    title=f"Use explicitly requested skill {explicit_skill}",
                    skill_name=explicit_skill,
                    skill_input={"operation": "execute", "task": task, "prompt": task},
                    selection_reason="explicit_skill_request",
                )
            ]

        urls = _URL_RE.findall(task)
        file_path = self._extract_path(task)
        steps: list[PlanStep] = []

        if file_path and self._allows_skill(request, "filesystem"):
            operation = "list_directory" if self._looks_like_directory_request(task) else "read_text_file"
            steps.append(
                PlanStep(
                    id=self._step_id(steps),
                    title=f"Use filesystem.{operation} for {file_path}",
                    skill_name="filesystem",
                    skill_input={"operation": operation, "path": file_path},
                    selection_reason="path_heuristic",
                )
            )

        if urls and self._allows_skill(request, "fetch"):
            steps.append(
                PlanStep(
                    id=self._step_id(steps),
                    title=f"Fetch content from {urls[0]}",
                    skill_name="fetch",
                    skill_input={"url": urls[0], "source": "direct_url"},
                    selection_reason="url_heuristic",
                )
            )
            return steps

        if self._is_research_task(task) and self._allows_skill(request, "web_search"):
            max_results = 5 if self._is_comparison_task(task) else 4
            fetch_limit = 3 if self._is_comparison_task(task) else 2
            steps.append(
                PlanStep(
                    id=self._step_id(steps),
                    title=f"Search web for: {task[:80]}",
                    skill_name="web_search",
                    skill_input={"query": self._search_query(task), "max_results": max_results, "timeout_seconds": 8.0},
                    selection_reason="research_heuristic",
                )
            )
            steps.append(
                PlanStep(
                    id=self._step_id(steps),
                    title="Fetch top search results",
                    skill_name="fetch",
                    skill_input={"from_search": True, "max_urls": fetch_limit},
                    selection_reason="research_followup",
                )
            )
            return steps

        if steps:
            return steps

        if self._is_research_task(task) and not self._allows_skill(request, "web_search"):
            return [PlanStep(id="step-1", title="Cannot perform research because web_search skill is disabled")]
        if urls:
            return [PlanStep(id="step-1", title="Cannot fetch URL because fetch skill is disabled")]
        if file_path or _FILE_HINT_RE.search(task):
            return [PlanStep(id="step-1", title="Cannot access filesystem because filesystem skill is disabled")]

        return [PlanStep(id="step-1", title="No executable tools inferred from task; provide a file path, URL, or explicit skill.")]

    @staticmethod
    def _step_id(steps: list[PlanStep]) -> str:
        return f"step-{len(steps) + 1}"

    @staticmethod
    def _search_query(task: str) -> str:
        cleaned = re.sub(r"\s+", " ", task).strip()
        return cleaned[:280]

    @staticmethod
    def _extract_explicit_skill(task: str) -> str | None:
        match = _EXPLICIT_SKILL_RE.search(task)
        return match.group(1).strip() if match else None

    @staticmethod
    def _is_research_task(task: str) -> bool:
        return bool(_RESEARCH_HINT_RE.search(task))

    @staticmethod
    def _is_comparison_task(task: str) -> bool:
        return bool(_COMPARE_HINT_RE.search(task))

    @staticmethod
    def _extract_path(task: str) -> str | None:
        quoted = re.search(r"[\"']([^\"']+)[\"']", task)
        if quoted and ("/" in quoted.group(1) or "." in quoted.group(1)):
            return quoted.group(1)

        path_match = re.search(r"(?:\./|/)[^\s]+", task)
        if path_match:
            return path_match.group(0)

        file_like = re.search(r"\b[\w\-/]+\.[a-zA-Z0-9]{1,8}\b", task)
        if file_like:
            return file_like.group(0)

        if re.search(r"list\s+(?:files|directory|dir)|repo", task, flags=re.IGNORECASE):
            return "."
        return None

    @staticmethod
    def _looks_like_directory_request(task: str) -> bool:
        return bool(re.search(r"list\s+(?:files|directory|dir)|show\s+files", task, flags=re.IGNORECASE))

    @staticmethod
    def _allows_skill(request: AgentRequest, skill_name: str) -> bool:
        if not request.enabled_skills:
            return True
        return skill_name in request.enabled_skills
