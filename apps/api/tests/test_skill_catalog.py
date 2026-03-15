import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from core.contracts import AgentRequest
from core.planner import Planner
from skills import MCPStdioConfig, MCPStdioSkill, SkillConfigField, SkillConfigValueType, SkillManifest, SkillRequest, SkillRuntimeType


def _mcp_manifest(script_path: Path, name: str = "echo_mcp_test", with_secret_config: bool = False) -> SkillManifest:
    config_fields = []
    env_map = {}
    test_input = {"prompt": "ping"}
    if with_secret_config:
        config_fields = [
            SkillConfigField(
                key="API_KEY",
                label="API key",
                description="Bind to an environment variable name",
                required=True,
                secret=True,
                value_type=SkillConfigValueType.STRING,
                env_var_allowed=True,
            )
        ]
        env_map = {"ECHO_API_KEY": "API_KEY"}
        test_input = {"prompt": "ping", "include_secret": True}

    return SkillManifest(
        name=name,
        version="0.1.0",
        description="Echo MCP test skill",
        runtime_type=SkillRuntimeType.MCP_STDIO,
        scopes=["local:test"],
        tags=["mcp", "test"],
        config_fields=config_fields,
        capabilities=[{"operation": "execute", "read_only": True}],
        mcp_stdio=MCPStdioConfig(
            command=sys.executable,
            args=[str(script_path)],
            tool_name="echo",
            env_map=env_map,
            test_input=test_input,
        ),
        test_input=test_input,
    )


def test_skill_manifest_validation_requires_mcp_config() -> None:
    try:
        SkillManifest(name="bad", description="bad", runtime_type=SkillRuntimeType.MCP_STDIO)
    except Exception as exc:  # noqa: BLE001
        assert "mcp_stdio configuration" in str(exc)
    else:
        raise AssertionError("Expected manifest validation to fail")


def test_skill_manifest_validation_rejects_secret_defaults() -> None:
    try:
        SkillConfigField(key="API_KEY", secret=True, default="bad")
    except Exception as exc:  # noqa: BLE001
        assert "Secret config fields cannot declare default values" in str(exc)
    else:
        raise AssertionError("Expected secret config validation to fail")


def test_mcp_stdio_skill_execute_and_test_with_redaction(monkeypatch) -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    secret_value = "super-secret-value"
    monkeypatch.setenv("TEST_ECHO_SECRET", secret_value)
    skill = MCPStdioSkill(
        _mcp_manifest(script_path, name="echo_mcp_direct", with_secret_config=True),
        runtime_env={"ECHO_API_KEY": secret_value},
        runtime_metadata={"config_readiness": "ready"},
        redact_values=[secret_value],
    )
    result = skill.execute(SkillRequest(operation="execute", input={"prompt": "hello", "include_secret": True}))
    assert result.success is True
    assert "[redacted]" in str(result.output.get("text", ""))
    assert secret_value not in str(result.output)
    test_result = skill.test()
    assert test_result.status.value == "passed"


def test_planner_routes_explicit_installed_skill() -> None:
    planner = Planner()
    plan = planner.create_plan(
        AgentRequest(task="Use skill echo_mcp_test to say hello", available_skills=["echo_mcp_test"], enabled_skills=["echo_mcp_test"])
    )
    assert plan[0].skill_name == "echo_mcp_test"
    assert plan[0].selection_reason == "explicit_skill_request"


def test_skill_catalog_routes_install_config_and_redact(monkeypatch) -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _mcp_manifest(script_path, name="echo_mcp_route_config", with_secret_config=True)
    secret_value = "route-secret-value"
    monkeypatch.setenv("AGENTHUB_TEST_SECRET", secret_value)

    with TestClient(app) as client:
        install = client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")})
        assert install.status_code == 200
        installed = install.json()
        assert installed["name"] == "echo_mcp_route_config"
        assert installed["readiness_status"] == "missing_required_env_binding"

        config_before = client.get("/skills/echo_mcp_route_config/config")
        assert config_before.status_code == 200
        assert config_before.json()["state"]["readiness_status"] == "missing_required_env_binding"

        configured = client.post(
            "/skills/echo_mcp_route_config/config",
            json={"values": {}, "secret_bindings": {"API_KEY": "AGENTHUB_TEST_SECRET"}},
        )
        assert configured.status_code == 200
        configured_payload = configured.json()
        assert configured_payload["readiness_status"] == "ready"
        assert json.dumps(configured_payload) .find(secret_value) == -1

        detail = client.get("/skills/echo_mcp_route_config/config")
        assert detail.status_code == 200
        detail_payload = detail.json()
        binding_state = next(item for item in detail_payload["state"]["values"] if item["key"] == "API_KEY")
        assert binding_state["secret_binding"] == "AGENTHUB_TEST_SECRET"
        assert binding_state["value"] is None

        tested = client.post("/skills/echo_mcp_route_config/test")
        assert tested.status_code == 200
        tested_payload = tested.json()
        assert tested_payload["status"] == "passed"
        assert secret_value not in json.dumps(tested_payload)


def test_skill_test_endpoint_reports_missing_env_value() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _mcp_manifest(script_path, name="echo_mcp_missing_env", with_secret_config=True)

    with TestClient(app) as client:
        install = client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")})
        assert install.status_code == 200

        configured = client.post(
            "/skills/echo_mcp_missing_env/config",
            json={"values": {}, "secret_bindings": {"API_KEY": "ENV_NAME_THAT_DOES_NOT_EXIST"}},
        )
        assert configured.status_code == 200
        assert configured.json()["readiness_status"] == "missing_required_env_binding"

        tested = client.post("/skills/echo_mcp_missing_env/test")
        assert tested.status_code == 200
        tested_payload = tested.json()
        assert tested_payload["status"] == "failed"
        assert "ENV_NAME_THAT_DOES_NOT_EXIST" in tested_payload["summary"]


def test_explicit_installed_skill_run_reports_config_failure() -> None:
    script_path = Path(__file__).parent / "fixtures" / "mcp_echo_server.py"
    manifest = _mcp_manifest(script_path, name="echo_mcp_run_blocked", with_secret_config=True)

    with TestClient(app) as client:
        install = client.post("/skills/install", json={"manifest": manifest.model_dump(mode="json")})
        assert install.status_code == 200

        create_run = client.post(
            "/runs",
            json={
                "task": "Use skill echo_mcp_run_blocked to say hello",
                "provider": "builtin",
                "model": "deterministic",
                "enabled_skills": ["echo_mcp_run_blocked"],
            },
        )
        assert create_run.status_code == 200
        run_payload = create_run.json()
        assert run_payload["run"]["status"] == "failed"
        assert "Missing required environment variable binding" in (run_payload["run"]["final_output"] or "")

        trace = client.get(f"/runs/{run_payload['run']['id']}/trace")
        assert trace.status_code == 200
        trace_payload = trace.json()
        tool_failed = next(item for item in trace_payload if item["event_type"] == "tool.failed")
        tool_failed_payload = json.loads(tool_failed["payload"])
        assert tool_failed_payload["config_readiness"] == "missing_required_env_binding"
        assert "Missing required environment variable binding" in tool_failed_payload["error"]
