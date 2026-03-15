import re

from .contracts import AgentRequest, PlanStep

_URL_RE = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
_FILE_HINT_RE = re.compile(
    r"(?:\./|/|[\w\-]+\.[a-zA-Z0-9]{1,8}|read\s+file|list\s+(?:files|directory|dir)|repo|directory)",
    re.IGNORECASE,
)


class Planner:
    """Deterministic planner for the alpha execution slice."""

    def create_plan(self, request: AgentRequest) -> list[PlanStep]:
        task = request.task.strip()
        urls = _URL_RE.findall(task)
        file_path = self._extract_path(task)
        steps: list[PlanStep] = []

        if file_path and self._allows_skill(request, "filesystem"):
            operation = "list_directory" if self._looks_like_directory_request(task) else "read_text_file"
            steps.append(
                PlanStep(
                    id="step-1",
                    title=f"Use filesystem.{operation} for {file_path}",
                    skill_name="filesystem",
                    skill_input={"operation": operation, "path": file_path},
                )
            )

        if urls and self._allows_skill(request, "fetch"):
            next_id = f"step-{len(steps) + 1}"
            steps.append(
                PlanStep(
                    id=next_id,
                    title=f"Fetch content from {urls[0]}",
                    skill_name="fetch",
                    skill_input={"url": urls[0]},
                )
            )

        if steps:
            return steps

        if urls:
            return [
                PlanStep(
                    id="step-1",
                    title="Cannot fetch URL because fetch skill is disabled",
                )
            ]

        if file_path or _FILE_HINT_RE.search(task):
            return [
                PlanStep(
                    id="step-1",
                    title="Cannot access filesystem because filesystem skill is disabled",
                )
            ]

        return [
            PlanStep(
                id="step-1",
                title="No executable tools inferred from task; provide a file path or URL.",
            )
        ]

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
