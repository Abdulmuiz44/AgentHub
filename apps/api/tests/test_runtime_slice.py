import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from core.contracts import AgentRequest
from core.executor import Executor
from core.planner import Planner
from core.contracts import EvidenceBundle, RunContext
from core.synthesis import SynthesisEngine
from core.tracing import TraceCollector
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


def test_planner_heuristics_url_file_and_research() -> None:
    planner = Planner()

    plan_fetch = planner.create_plan(AgentRequest(task="Fetch https://example.com", enabled_skills=["fetch"]))
    assert plan_fetch[0].skill_name == "fetch"

    plan_fs = planner.create_plan(AgentRequest(task="Read README.md", enabled_skills=["filesystem"]))
    assert plan_fs[0].skill_name == "filesystem"
    assert plan_fs[0].skill_input["operation"] == "read_text_file"

    plan_research = planner.create_plan(
        AgentRequest(task="Research and compare python and golang web frameworks", enabled_skills=["web_search", "fetch"])
    )
    assert len(plan_research) >= 2
    assert plan_research[0].skill_name == "web_search"
    assert plan_research[1].skill_name == "fetch"
    assert plan_research[1].skill_input["from_search"] is True


def test_filesystem_guardrails(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
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
                if name == "Content-Type":
                    return "text/plain"
                return default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"sample body"

    def fake_urlopen(_request, timeout: float):
        assert timeout > 0
        return FakeResponse()

    monkeypatch.setattr("skills.fetch.urlopen", fake_urlopen)
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    skill = FetchSkill()
    result = skill.execute(SkillRequest(input={"url": "https://example.com"}))
    assert result.success is True
    assert "sample body" in result.output["text"]


def test_web_search_skill_deduplicates_results(monkeypatch) -> None:
    monkeypatch.setattr("skills.search_provider.socket.getaddrinfo", lambda *_args, **_kwargs: [])
    skill = WebSearchSkill(resolver=StubSearchResolver())
    result = skill.execute(SkillRequest(input={"query": "research language", "max_results": 5}))
    assert result.success is True
    urls = [item["url"] for item in result.output["results"]]
    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_executor_multi_step_search_fetch(monkeypatch) -> None:
    monkeypatch.setattr("skills.search_provider.socket.getaddrinfo", lambda *_args, **_kwargs: [])

    class FakeFetchSkill(FetchSkill):
        def execute(self, request: SkillRequest):
            url = request.input["url"]
            return super().execute(SkillRequest(input={"url": url}))

    class FakeResponse:
        status = 200

        class headers:
            @staticmethod
            def get(name: str, default: str = "") -> str:
                if name == "Content-Type":
                    return "text/plain"
                return default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"fetched sample text"

    monkeypatch.setattr("skills.fetch.urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    registry = SkillRegistry(
        {
            "web_search": WebSearchSkill(resolver=StubSearchResolver()),
            "fetch": FakeFetchSkill(),
        }
    )
    executor = Executor(registry)
    steps = Planner().create_plan(
        AgentRequest(task="Research compare tools", enabled_skills=["web_search", "fetch"])
    )
    result = executor.execute(context=RunContext(run_id=1), steps=steps, trace_collector=TraceCollector())
    assert result.status.value == "completed"
    assert result.execution_summary["evidence_items"] >= 2


def test_fallback_synthesis_uses_evidence() -> None:
    engine = SynthesisEngine()
    output, meta = engine.synthesize(
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


def test_run_execution_and_trace_routes(monkeypatch) -> None:
    monkeypatch.setattr("skills.search_provider.socket.getaddrinfo", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("skills.search_provider.DuckDuckGoInstantSearchProvider.search", lambda _self, request: SearchProviderResponse(query=request.query, results=[SearchResultItem(title="Demo", url="https://example.com/demo", snippet="demo snippet", rank=1)]))

    class FakeResponse:
        status = 200

        class headers:
            @staticmethod
            def get(name: str, default: str = "") -> str:
                if name == "Content-Type":
                    return "text/plain"
                return default

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size: int) -> bytes:
            return b"research body"

    monkeypatch.setattr("skills.fetch.urlopen", lambda *_args, **_kwargs: FakeResponse())
    monkeypatch.setattr("skills.fetch.socket.getaddrinfo", lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 0))])

    with TestClient(app) as client:
        create_run = client.post(
            "/runs",
            json={
                "task": "Research compare python and golang web frameworks",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["web_search", "fetch"],
                "execute_now": True,
            },
        )
        assert create_run.status_code == 200
        payload = create_run.json()
        run_id = payload["run"]["id"]
        assert payload["run"]["status"] in {"completed", "failed"}
        assert payload["run"]["final_output"]
        assert payload["run"]["synthesis_mode"] == "deterministic_fallback"
        assert payload["run"]["synthesis_provider"] == "builtin"
        assert payload["run"]["synthesis_model"] == "deterministic"
        assert payload["run"]["output"] == payload["run"]["final_output"]
        assert isinstance(payload["run"]["plan"], list)
        assert isinstance(payload["run"]["step_results"], list)
        assert "evidence_summary" in payload["run"]

        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200
        run_body = get_run.json()
        assert "final_output" in run_body
        assert run_body["output"] == run_body["final_output"]
        assert "synthesis_status" in run_body

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        event_types = [item["event_type"] for item in trace.json()]
        assert "run.started" in event_types
        assert "plan.created" in event_types
        assert "tool.requested" in event_types
        assert "synthesis.started" in event_types
        assert "synthesis.completed" in event_types
        assert event_types[-1] in {"run.completed", "run.failed"}

        plan_event = next(item for item in trace.json() if item["event_type"] == "plan.created")
        payload_data = json.loads(plan_event["payload"])
        assert "plan" in payload_data
