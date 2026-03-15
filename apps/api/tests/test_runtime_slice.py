import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from core.contracts import AgentRequest
from core.planner import Planner
from skills.fetch import FetchSkill
from skills.base import SkillRequest
from skills.filesystem import FilesystemConfig, FilesystemSkill


def test_planner_heuristics_url_and_file() -> None:
    planner = Planner()

    plan_fetch = planner.create_plan(AgentRequest(task="Fetch https://example.com", enabled_skills=["fetch"]))
    assert plan_fetch[0].skill_name == "fetch"

    plan_fs = planner.create_plan(AgentRequest(task="Read README.md", enabled_skills=["filesystem"]))
    assert plan_fs[0].skill_name == "filesystem"
    assert plan_fs[0].skill_input["operation"] == "read_text_file"


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


def test_run_execution_and_trace_routes() -> None:
    with TestClient(app) as client:
        create_run = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )
        assert create_run.status_code == 200
        payload = create_run.json()
        run_id = payload["run"]["id"]
        assert payload["run"]["status"] in {"completed", "failed"}
        assert payload["run"]["final_output"]

        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200
        assert "final_output" in get_run.json()

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        event_types = [item["event_type"] for item in trace.json()]
        assert "run.started" in event_types
        assert "plan.created" in event_types
        assert event_types[-1] in {"run.completed", "run.failed"}

        plan_event = next(item for item in trace.json() if item["event_type"] == "plan.created")
        payload_data = json.loads(plan_event["payload"])
        assert "plan" in payload_data
