import json
import shutil
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.db.session import engine
from app.main import app
from core.contracts import (
    AgentRequest,
    ApprovalStatus,
    EvidenceBundle,
    ExecutionBudget,
    ExecutionMode,
    ExecutionState,
    PlanStep,
    PlanningSkillDescriptor,
    PlanningSource,
    RunContext,
)
from core.executor import Executor
from core.planner import Planner
from core.planning_service import PlanningService
from core.synthesis import SynthesisEngine
from core.tracing import TraceCollector
from memory.runs import get_run
from models import ProviderAdapter, ProviderCapability, ProviderGenerationRequest, ProviderGenerationResponse, ProviderHealthCheck
from skills import MCPStdioConfig, SkillManifest, SkillRuntimeType
from skills.base import SkillRequest
from skills.fetch import FetchSkill
from skills.filesystem import FilesystemConfig, FilesystemSkill
from skills.registry import SkillRegistry
from skills.search_provider import SearchProvider, SearchProviderRequest, SearchProviderResponse, SearchResultItem
from skills.web_search import WebSearchSkill


class StubSearchProvider(SearchProvider):
    name = "stub"

    def search(self, request: SearchProviderRequest) -> SearchProviderResponse:
        return SearchProviderResponse(
            query=request.query,
            results=[
                SearchResultItem(title="A", url="https://example.com/a", snippet="one", rank=1),
                SearchResultItem(title="A duplicate", url="https://example.com/a", snippet="dup", rank=2),
                SearchResultItem(title="B", url="https://example.com/b", snippet="two", rank=3),
            ],
        )


class StubSearchResolver:
    def resolve(self) -> SearchProvider:
        return StubSearchProvider()


class StubPlanningAdapter(ProviderAdapter):
    def __init__(self, output_text: str, *, provider_name: str = "ollama") -> None:
        self._output_text = output_text
        self._provider_name = provider_name

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(name=self._provider_name, display_name=self._provider_name.title(), models=["stub-model"], supports_streaming=False)

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def default_timeout(self) -> float:
        return 5.0

    def health_check(self) -> ProviderHealthCheck:
        return ProviderHealthCheck(provider=self._provider_name, healthy=True, message="ok")

    def list_models(self) -> list[str]:
        return ["stub-model"]

    def generate(self, request: ProviderGenerationRequest) -> ProviderGenerationResponse:
        if request.metadata.get("purpose") == "planning":
            return ProviderGenerationResponse(provider=self._provider_name, model=request.model, output_text=self._output_text)
        return ProviderGenerationResponse(provider=self._provider_name, model=request.model, output_text="provider synthesis output")


def _approval_manifest(script_path: Path, name: str) -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description="Approval gated MCP skill",
        runtime_type=SkillRuntimeType.MCP_STDIO,
        scopes=["local:test"],
        tags=["mcp", "approval"],
        capability_categories=["custom_tool"],
        capabilities=[{"operation": "execute", "read_only": False}],
        mcp_stdio=MCPStdioConfig(
            command=sys.executable,
            args=[str(script_path)],
            tool_name="echo",
            test_input={"prompt": "ping"},
        ),
        test_input={"prompt": "ping"},
    )


def wait_for_status(client: TestClient, run_id: int, statuses: set[str], timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    worker = client.app.state.run_worker
    while time.time() < deadline:
        worker.wait_for_idle(timeout=0.2)
        payload = client.get(f"/runs/{run_id}")
        assert payload.status_code == 200
        run = payload.json()
        if run["status"] in statuses:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach one of {statuses}")


def test_planner_heuristics_url_file_and_research() -> None:
    planner = Planner()

    plan_fetch = planner.create_plan(AgentRequest(task="Fetch https://example.com", enabled_skills=["fetch"]))
    assert plan_fetch[0].skill_name == "fetch"

    plan_fs = planner.create_plan(AgentRequest(task="Read README.md", enabled_skills=["filesystem"]))
    assert plan_fs[0].skill_name == "filesystem"
    assert plan_fs[0].skill_input["operation"] == "read_text_file"

    plan_research = planner.create_plan(AgentRequest(task="Research and compare python and golang web frameworks", enabled_skills=["web_search", "fetch"]))
    assert len(plan_research) >= 2
    assert plan_research[0].skill_name == "web_search"
    assert plan_research[1].skill_name == "fetch"
    assert plan_research[1].skill_input["from_search"] is True


def test_planner_treats_repo_search_as_research_not_filesystem() -> None:
    planner = Planner()

    plan = planner.create_plan(
        AgentRequest(
            task="look for ai agents repo on github",
            enabled_skills=["filesystem", "web_search", "fetch"],
        )
    )

    assert len(plan) >= 2
    assert plan[0].skill_name == "web_search"
    assert plan[1].skill_name == "fetch"


def test_filesystem_guardrails() -> None:
    workspace = Path(".tmp/test-filesystem-guardrails")
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    skill = FilesystemSkill(FilesystemConfig(workspace_root=workspace, max_file_size_bytes=10))

    ok = skill.execute(SkillRequest(operation="read_text_file", input={"path": "notes.txt"}))
    assert ok.success is True

    bad = skill.execute(SkillRequest(operation="read_text_file", input={"path": "../secret.txt"}))
    assert bad.success is False


def test_fetch_skill_with_mocked_response(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        class headers:
            @staticmethod
            def get(name: str, default: str = "") -> str:
                return "text/plain" if name == "Content-Type" else default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"sample body"

    monkeypatch.setattr("skills.fetch.urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    result = FetchSkill().execute(SkillRequest(input={"url": "https://example.com"}))
    assert result.success is True
    assert "sample body" in result.output["text"]


def test_web_search_skill_deduplicates_results(monkeypatch) -> None:
    monkeypatch.setattr("skills.search_provider.socket.getaddrinfo", lambda *_args, **_kwargs: [])
    skill = WebSearchSkill(resolver=StubSearchResolver())
    result = skill.execute(SkillRequest(input={"query": "research language", "max_results": 5}))
    assert result.success is True
    urls = [item["url"] for item in result.output["results"]]
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_planning_service_uses_provider_plan() -> None:
    planning = PlanningService(provider_registry=None)
    planning.provider_registry = type("StubRegistry", (), {"get": lambda _self, _name: StubPlanningAdapter(json.dumps({
        "decision_summary": "search then fetch",
        "steps": [
            {"title": "Search web", "skill_name": "web_search", "skill_input": {"query": "latest docs"}, "decision_summary": "Need discovery"},
            {"title": "Fetch result", "skill_name": "fetch", "skill_input": {"url": "https://example.com"}, "decision_summary": "Need source text"},
        ],
    }))})()
    request = AgentRequest(
        task="Find the latest docs",
        provider="ollama",
        model="stub-model",
        execution_mode=ExecutionMode.MODEL_ASSISTED,
        planning_skills=[
            PlanningSkillDescriptor(name="web_search", runtime_type="native_python", description="Search", scopes=[], capability_categories=["web_search"], readiness="ready"),
            PlanningSkillDescriptor(name="fetch", runtime_type="native_python", description="Fetch", scopes=[], capability_categories=["web_fetch"], readiness="ready"),
        ],
        budget=ExecutionBudget(),
    )
    outcome = planning.create_plan(request)
    assert outcome.planning_source.value == "provider"
    assert [step.skill_name for step in outcome.plan] == ["web_search", "fetch"]


def test_executor_budget_enforcement(monkeypatch) -> None:
    class FakeResponse:
        status = 200

        class headers:
            @staticmethod
            def get(name: str, default: str = "") -> str:
                return "text/plain" if name == "Content-Type" else default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"budgeted fetch"

    monkeypatch.setattr("skills.fetch.urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    registry = SkillRegistry({"fetch": FetchSkill()})
    executor = Executor(registry)
    state = executor.execute_steps(
        context=RunContext(run_id=1),
        steps=[
            PlanStep(id="step-1", title="Fetch A", skill_name="fetch", skill_input={"url": "https://example.com/a"}),
            PlanStep(id="step-2", title="Fetch B", skill_name="fetch", skill_input={"url": "https://example.com/b"}),
        ],
        trace_collector=TraceCollector(),
        budget=ExecutionBudget(max_tool_invocations=1),
        checkpoint=ExecutionState(),
    )
    assert state.budget_usage_summary["tool_invocations"] == 1
    assert state.budget_usage_summary["budget_blocked"]


def test_fallback_synthesis_uses_evidence() -> None:
    engine_instance = SynthesisEngine()
    output, meta = engine_instance.synthesize(
        task="Compare options",
        provider="builtin",
        model="deterministic",
        plan=[],
        step_results=[],
        execution_summary={"steps_total": 2},
        evidence=EvidenceBundle(
            items=[
                {"source_type": "web_page", "source_ref": "https://a", "title": "A", "excerpt": "A is fast", "metadata": {}},
                {"source_type": "web_page", "source_ref": "https://b", "title": "B", "excerpt": "B is cheap", "metadata": {}},
            ],
            notes=["one source timed out"],
        ),
    )
    assert meta.mode == "deterministic_fallback"
    assert "Source references" in output


def test_post_runs_returns_queued_and_worker_completes() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/runs",
            json={
                "task": "Summarize README.md",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["filesystem"],
            },
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["run"]["status"] == "queued"
        run = wait_for_status(client, payload["run"]["id"], {"completed", "failed"})
        assert run["status"] in {"completed", "failed"}
        trace = client.get(f"/runs/{payload['run']['id']}/trace").json()
        event_types = [item["event_type"] for item in trace]
        assert "run.queued" in event_types
        assert "run.started" in event_types


def test_approval_pause_and_resume() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _approval_manifest(script_path, "approval_resume_skill")

    with TestClient(app) as client:
        installed = client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")})
        assert installed.status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill approval_resume_skill to say hello",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["approval_resume_skill"],
            },
        )
        assert created.status_code == 200
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert waiting["pending_approval"] is not None

        with Session(engine) as db:
            persisted = get_run(db, run_id)
            assert persisted is not None
            assert persisted.execution_state["current_step_index"] == 0
            assert persisted.execution_state["pending_approval_id"] == waiting["pending_approval"]["id"]

        approved = client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve")
        assert approved.status_code == 200
        final = wait_for_status(client, run_id, {"completed"})
        assert final["status"] == "completed"
        trace = client.get(f"/runs/{run_id}/trace").json()
        event_types = [item["event_type"] for item in trace]
        assert "approval.requested" in event_types
        assert "run.paused" in event_types
        assert "approval.resolved" in event_types
        assert "run.resumed" in event_types


def test_approval_deny_terminates_run() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _approval_manifest(script_path, "approval_deny_skill")

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill approval_deny_skill to say hello",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["approval_deny_skill"],
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        denied = client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/deny")
        assert denied.status_code == 200
        failed = wait_for_status(client, run_id, {"failed"})
        assert failed["status"] == "failed"


def test_cancel_queued_run() -> None:
    with TestClient(app) as client:
        worker = client.app.state.run_worker
        worker.stop()
        created = client.post(
            "/runs",
            json={
                "task": "Summarize README.md",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["filesystem"],
            },
        )
        assert created.status_code == 200
        run_id = created.json()["run"]["id"]
        cancelled = client.post(f"/runs/{run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        worker.start()


def test_cancel_waiting_run() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _approval_manifest(script_path, "approval_cancel_skill")

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill approval_cancel_skill to say hello",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["approval_cancel_skill"],
            },
        )
        run_id = created.json()["run"]["id"]
        wait_for_status(client, run_id, {"waiting_for_approval"})
        cancelled = client.post(f"/runs/{run_id}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


def test_stream_returns_live_progress_events() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/runs",
            json={
                "task": "Summarize README.md",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["filesystem"],
            },
        )
        run_id = created.json()["run"]["id"]
        wait_for_status(client, run_id, {"completed", "failed"})
        with client.stream("GET", f"/runs/{run_id}/stream") as response:
            body = "".join(chunk for chunk in response.iter_text())
        assert '"type": "run"' in body
        assert '"type": "trace"' in body


def test_model_assisted_run_works_under_worker(monkeypatch) -> None:
    monkeypatch.setattr("skills.search_provider.socket.getaddrinfo", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("skills.search_provider.DuckDuckGoInstantSearchProvider.search", lambda _self, request: SearchProviderResponse(query=request.query, results=[SearchResultItem(title="Demo", url="https://example.com/demo", snippet="demo snippet", rank=1)]))
    monkeypatch.setattr("models.registry.ProviderRegistry.get", lambda _self, name: StubPlanningAdapter(json.dumps({
        "decision_summary": "search then fetch",
        "steps": [
            {"title": "Search", "skill_name": "web_search", "skill_input": {"query": "python golang frameworks"}, "decision_summary": "Need candidates"},
            {"title": "Fetch", "skill_name": "fetch", "skill_input": {"url": "https://example.com/demo"}, "decision_summary": "Need source"},
        ],
    })) if name == "ollama" else None)

    class FakeResponse:
        status = 200

        class headers:
            @staticmethod
            def get(name: str, default: str = "") -> str:
                return "text/plain" if name == "Content-Type" else default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"research body"

    monkeypatch.setattr("skills.fetch.urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    with TestClient(app) as client:
        created = client.post(
            "/runs",
            json={
                "task": "Research compare python and golang web frameworks",
                "provider": "ollama",
                "model": "stub-model",
                "enabled_skills": ["web_search", "fetch"],
                "execution_mode": "model_assisted",
            },
        )
        assert created.status_code == 200
        run_id = created.json()["run"]["id"]
        final = wait_for_status(client, run_id, {"completed", "failed"})
        assert final["execution_mode"] == "model_assisted"
        trace = client.get(f"/runs/{run_id}/trace").json()
        event_types = [item["event_type"] for item in trace]
        assert "planning.started" in event_types
        assert "planning.completed" in event_types







def _mutation_manifest(script_path: Path, name: str) -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description="Mutation MCP test skill",
        runtime_type=SkillRuntimeType.MCP_STDIO,
        scopes=["local:test"],
        tags=["mcp", "mutation"],
        capability_categories=["custom_tool"],
        capabilities=[{"operation": "mutate", "read_only": False}],
        mcp_stdio=MCPStdioConfig(
            command=sys.executable,
            args=[str(script_path)],
            tool_name="mutate",
            test_input={"prompt": "write file .tmp/review-first/test.txt with content hello"},
        ),
    )


def test_review_first_run_proposes_changes_and_apply_flow() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_mutation_server.py"
    manifest = _mutation_manifest(script_path, "review_first_mutation_skill")
    target_path = Path(".tmp/review-first/proposed.txt")
    if target_path.exists():
        target_path.unlink()

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill review_first_mutation_skill to write file .tmp/review-first/proposed.txt with content pending-review",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["review_first_mutation_skill"],
                "mutation_apply_mode": "review_first",
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert waiting["pending_approval"] is not None
        assert client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve").status_code == 200
        review = wait_for_status(client, run_id, {"waiting_for_review"})
        assert review["pending_change_count"] == 1
        assert not target_path.exists()

        changes = client.get(f"/runs/{run_id}/changes")
        assert changes.status_code == 200
        payload = changes.json()
        assert payload[0]["status"] == "pending"
        assert payload[0]["files"][0]["path"] == ".tmp/review-first/proposed.txt"
        assert "+++ b/.tmp/review-first/proposed.txt" in payload[0]["files"][0]["diff_preview"]

        applied = client.post(f"/runs/{run_id}/apply")
        assert applied.status_code == 200
        assert applied.json()["run"]["status"] == "completed"
        assert target_path.read_text(encoding="utf-8") == "pending-review"
        trace = client.get(f"/runs/{run_id}/trace").json()
        event_types = [item["event_type"] for item in trace]
        assert "change.proposed" in event_types
        assert "change.review_pending" in event_types
        assert "change.apply_requested" in event_types
        assert "change.applied" in event_types


def test_reject_review_first_changes_preserves_workspace() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_mutation_server.py"
    manifest = _mutation_manifest(script_path, "reject_mutation_skill")
    target_path = Path(".tmp/review-first/rejected.txt")
    if target_path.exists():
        target_path.unlink()

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill reject_mutation_skill to write file .tmp/review-first/rejected.txt with content reject-me",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["reject_mutation_skill"],
                "mutation_apply_mode": "review_first",
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve").status_code == 200
        wait_for_status(client, run_id, {"waiting_for_review"})
        rejected = client.post(f"/runs/{run_id}/reject")
        assert rejected.status_code == 200
        assert rejected.json()["run"]["review_status"] == "rejected"
        assert not target_path.exists()


def test_direct_apply_mutation_preserves_current_behavior() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_mutation_server.py"
    manifest = _mutation_manifest(script_path, "direct_apply_mutation_skill")
    target_path = Path(".tmp/review-first/direct.txt")
    if target_path.exists():
        target_path.unlink()

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill direct_apply_mutation_skill to write file .tmp/review-first/direct.txt with content direct-write",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["direct_apply_mutation_skill"],
                "mutation_apply_mode": "direct_apply",
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve").status_code == 200
        final = wait_for_status(client, run_id, {"completed", "failed"})
        assert final["status"] == "completed"
        assert target_path.read_text(encoding="utf-8") == "direct-write"
        changes = client.get(f"/runs/{run_id}/changes")
        assert changes.status_code == 200
        assert changes.json() == []


def test_apply_blocks_when_workspace_is_stale() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_mutation_server.py"
    manifest = _mutation_manifest(script_path, "stale_mutation_skill")
    target_path = Path(".tmp/review-first/stale.txt")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("base", encoding="utf-8")

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use skill stale_mutation_skill to write file .tmp/review-first/stale.txt with content new-value",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["stale_mutation_skill"],
                "mutation_apply_mode": "review_first",
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve").status_code == 200
        wait_for_status(client, run_id, {"waiting_for_review"})
        target_path.write_text("mutated-outside", encoding="utf-8")
        blocked = client.post(f"/runs/{run_id}/apply")
        assert blocked.status_code == 409
        trace = client.get(f"/runs/{run_id}/trace").json()
        assert "change.apply_failed" in [item["event_type"] for item in trace]


def test_model_assisted_review_first_allows_mutation_skill(monkeypatch) -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_mutation_server.py"
    manifest = _mutation_manifest(script_path, "model_review_mutation_skill")
    monkeypatch.setattr(
        "models.registry.ProviderRegistry.get",
        lambda _self, name: StubPlanningAdapter(json.dumps({
            "decision_summary": "propose one file change",
            "steps": [{"title": "Mutate file", "skill_name": "model_review_mutation_skill", "skill_input": {"prompt": "write file .tmp/review-first/model.txt with content model-review"}, "decision_summary": "Need a mutation step"}],
        })) if name == "ollama" else None,
    )

    with TestClient(app) as client:
        assert client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")}).status_code == 200
        created = client.post(
            "/runs",
            json={
                "task": "Use the installed mutation skill",
                "provider": "ollama",
                "model": "stub-model",
                "enabled_skills": ["model_review_mutation_skill"],
                "execution_mode": "model_assisted",
                "mutation_apply_mode": "review_first",
            },
        )
        run_id = created.json()["run"]["id"]
        waiting = wait_for_status(client, run_id, {"waiting_for_approval"})
        assert client.post(f"/runs/{run_id}/approvals/{waiting['pending_approval']['id']}/approve").status_code == 200
        review = wait_for_status(client, run_id, {"waiting_for_review"})
        assert review["mutation_apply_mode"] == "review_first"
