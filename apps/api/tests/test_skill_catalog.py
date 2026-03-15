import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from core.contracts import AgentRequest
from core.planner import Planner
from skills import MCPStdioConfig, MCPStdioSkill, SkillManifest, SkillRequest, SkillRuntimeType


def _mcp_manifest(script_path: Path, name: str = "echo_mcp_test") -> SkillManifest:
    return SkillManifest(
        name=name,
        version="0.1.0",
        description="Echo MCP test skill",
        runtime_type=SkillRuntimeType.MCP_STDIO,
        scopes=["local:test"],
        tags=["mcp", "test"],
        capabilities=[{"operation": "execute", "read_only": True}],
        mcp_stdio=MCPStdioConfig(command=sys.executable, args=[str(script_path)], tool_name="echo", test_input={"prompt": "ping"}),
        test_input={"prompt": "ping"},
    )


def test_skill_manifest_validation_requires_mcp_config() -> None:
    try:
        SkillManifest(name="bad", description="bad", runtime_type=SkillRuntimeType.MCP_STDIO)
    except Exception as exc:  # noqa: BLE001
        assert "mcp_stdio configuration" in str(exc)
    else:
        raise AssertionError("Expected manifest validation to fail")


def test_mcp_stdio_skill_execute_and_test() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    skill = MCPStdioSkill(_mcp_manifest(script_path, name="echo_mcp_direct"))
    result = skill.execute(SkillRequest(operation="execute", input={"prompt": "hello"}))
    assert result.success is True
    assert "echo:hello" in str(result.output.get("text", ""))
    test_result = skill.test()
    assert test_result.status.value == "passed"


def test_planner_routes_explicit_installed_skill() -> None:
    planner = Planner()
    plan = planner.create_plan(
        AgentRequest(task="Use skill echo_mcp_test to say hello", available_skills=["echo_mcp_test"], enabled_skills=["echo_mcp_test"])
    )
    assert plan[0].skill_name == "echo_mcp_test"
    assert plan[0].selection_reason == "explicit_skill_request"


def test_skill_catalog_routes_install_toggle_and_test() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _mcp_manifest(script_path, name="echo_mcp_route")

    with TestClient(app) as client:
        skills = client.get("/skills")
        assert skills.status_code == 200
        payload = skills.json()
        filesystem = next(item for item in payload if item["name"] == "filesystem")
        assert filesystem["runtime_type"] == "native_python"
        assert filesystem["enabled"] is True

        install = client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")})
        assert install.status_code == 200
        installed = install.json()
        assert installed["name"] == "echo_mcp_route"
        assert installed["runtime_type"] == "mcp_stdio"

        disabled = client.post("/skills/echo_mcp_route/disable")
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False

        enabled = client.post("/skills/echo_mcp_route/enable")
        assert enabled.status_code == 200
        assert enabled.json()["enabled"] is True

        tested = client.post("/skills/echo_mcp_route/test")
        assert tested.status_code == 200
        tested_payload = tested.json()
        assert tested_payload["status"] == "passed"
        assert tested_payload["skill"]["last_test_status"] == "passed"
