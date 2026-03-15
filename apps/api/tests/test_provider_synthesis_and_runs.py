import json

from fastapi.testclient import TestClient

from app.main import app
from core.contracts import PlanStep, StepExecutionResult
from core.synthesis import SynthesisEngine
from models.base import (
    ProviderAdapter,
    ProviderCapability,
    ProviderError,
    ProviderGenerationRequest,
    ProviderGenerationResponse,
    ProviderHealthCheck,
)
from models.registry import ProviderConfigurationStatus, ProviderRegistry


class FakeProviderAdapter(ProviderAdapter):
    def __init__(
        self,
        *,
        name: str = "ollama",
        models: list[str] | None = None,
        listed_models: list[str] | None = None,
        health: ProviderHealthCheck | None = None,
        generation_response: ProviderGenerationResponse | None = None,
    ) -> None:
        self._name = name
        self._models = models or ["llama3.1"]
        self._listed_models = listed_models if listed_models is not None else self._models
        self._health = health or ProviderHealthCheck(provider=name, healthy=True, message="ok")
        self._generation_response = generation_response or ProviderGenerationResponse(
            provider=name,
            model=self._models[0],
            output_text="mocked synthesis output",
        )
        self.generate_requests: list[ProviderGenerationRequest] = []

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(name=self._name, display_name=self._name.title(), models=self._models, supports_streaming=False)

    @property
    def provider_name(self) -> str:
        return self._name

    @property
    def default_timeout(self) -> float:
        return 0.1

    def health_check(self) -> ProviderHealthCheck:
        return self._health

    def list_models(self) -> list[str]:
        return self._listed_models

    def generate(self, request: ProviderGenerationRequest) -> ProviderGenerationResponse:
        self.generate_requests.append(request)
        return self._generation_response


def _plan() -> list[PlanStep]:
    return [PlanStep(id="step-1", title="Read file", skill_name="filesystem", skill_input={"path": "README.md"})]


def _results() -> list[StepExecutionResult]:
    return [StepExecutionResult(step_id="step-1", success=True, summary="Read complete")]


def test_provider_registry_configuration_and_lookup_get_semantics(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTHUB_OPENAI_API_KEY", raising=False)

    registry = ProviderRegistry.default()

    openai_lookup = registry.get_by_name("openai")
    assert openai_lookup.exists is True
    assert openai_lookup.configuration_status == ProviderConfigurationStatus.UNCONFIGURED
    assert registry.get("openai") is None

    ollama_lookup = registry.get_by_name("ollama")
    assert ollama_lookup.exists is True
    assert ollama_lookup.configuration_status == ProviderConfigurationStatus.CONFIGURED
    assert registry.get("ollama") is not None

    missing_lookup = registry.get_by_name("missing")
    assert missing_lookup.exists is False
    assert missing_lookup.configuration_status == ProviderConfigurationStatus.UNKNOWN
    assert registry.get("missing") is None


def test_synthesis_engine_fallback_builtin_unconfigured_and_missing(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTHUB_OPENAI_API_KEY", raising=False)
    engine = SynthesisEngine()

    builtin_output, builtin_meta = engine.synthesize(
        task="Task",
        provider="builtin",
        model="deterministic",
        plan=_plan(),
        step_results=_results(),
        execution_summary="summary",
    )
    assert builtin_output
    assert builtin_meta.mode == "deterministic_fallback"
    assert "configuration missing" in (builtin_meta.error_summary or "")

    unconfigured_output, unconfigured_meta = engine.synthesize(
        task="Task",
        provider="openai",
        model="gpt-4o-mini",
        plan=_plan(),
        step_results=_results(),
        execution_summary="summary",
    )
    assert unconfigured_output
    assert unconfigured_meta.mode == "deterministic_fallback"
    assert "Provider not found: openai" in (unconfigured_meta.error_summary or "")

    missing_output, missing_meta = engine.synthesize(
        task="Task",
        provider="missing",
        model="x",
        plan=_plan(),
        step_results=_results(),
        execution_summary="summary",
    )
    assert missing_output
    assert missing_meta.mode == "deterministic_fallback"
    assert "Provider not found: missing" in (missing_meta.error_summary or "")


def test_synthesis_engine_provider_success_path_with_response_output_text() -> None:
    adapter = FakeProviderAdapter(
        generation_response=ProviderGenerationResponse(provider="ollama", model="llama3.1", output_text="provider text")
    )
    registry = ProviderRegistry()
    registry.register(adapter)
    engine = SynthesisEngine(provider_registry=registry)

    output, metadata = engine.synthesize(
        task="Task",
        provider="ollama",
        model="llama3.1",
        plan=_plan(),
        step_results=_results(),
        execution_summary="summary",
    )

    assert output == "provider text"
    assert metadata.mode == "provider"
    assert metadata.status == "completed"
    assert len(adapter.generate_requests) == 1
    assert adapter.generate_requests[0].messages[0].content.startswith("Synthesize final run output")


def test_synthesis_engine_provider_error_response_falls_back_with_error_summary() -> None:
    adapter = FakeProviderAdapter(
        generation_response=ProviderGenerationResponse(
            provider="ollama",
            model="llama3.1",
            error=ProviderError(code="rate_limited", message="too many requests", retryable=True),
        )
    )
    registry = ProviderRegistry()
    registry.register(adapter)
    engine = SynthesisEngine(provider_registry=registry)

    output, metadata = engine.synthesize(
        task="Task",
        provider="ollama",
        model="llama3.1",
        plan=_plan(),
        step_results=_results(),
        execution_summary="summary",
    )

    assert output
    assert metadata.mode == "deterministic_fallback"
    assert metadata.error_summary == "rate_limited: too many requests"


def test_provider_endpoints_list_shape_models_and_health_check(monkeypatch) -> None:
    configured_adapter = FakeProviderAdapter(
        listed_models=["custom-a", "custom-b"],
        health=ProviderHealthCheck(provider="ollama", healthy=True, message="healthy"),
    )
    openai_adapter = FakeProviderAdapter(name="openai", models=["gpt-4o-mini"], listed_models=["should-not-be-used"])

    registry = ProviderRegistry()
    registry.register(configured_adapter)
    registry.register(openai_adapter)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AGENTHUB_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("app.api.routes.providers.ProviderRegistry.default", lambda: registry)

    with TestClient(app) as client:
        providers = client.get("/providers")
        assert providers.status_code == 200
        body = providers.json()
        by_name = {item["provider"]["name"]: item for item in body}
        assert by_name["ollama"]["configuration_status"] == "configured"
        assert by_name["ollama"]["is_configured"] is True
        assert by_name["openai"]["configuration_status"] == "unconfigured"
        assert by_name["openai"]["is_configured"] is False

        models = client.get("/providers/models")
        assert models.status_code == 200
        models_body = {item["provider_name"]: item for item in models.json()["providers"]}
        assert models_body["ollama"]["models"] == ["custom-a", "custom-b"]
        assert models_body["openai"]["models"] == ["gpt-4o-mini"]

        health_ok = client.post("/providers/health-check", json={"provider": "ollama"})
        assert health_ok.status_code == 200
        assert health_ok.json()["healthy"] is True
        assert health_ok.json()["message"] == "healthy"

        health_unconfigured = client.post("/providers/health-check", json={"provider": "openai"})
        assert health_unconfigured.status_code == 200
        assert health_unconfigured.json()["healthy"] is False
        assert health_unconfigured.json()["message"] == "Provider is not configured"

        health_unknown = client.post("/providers/health-check", json={"provider": "missing"})
        assert health_unknown.status_code == 404


def test_provider_models_endpoint_handles_list_models_failure(monkeypatch) -> None:
    adapter = FakeProviderAdapter(models=["capability-default"], listed_models=[])
    registry = ProviderRegistry()
    registry.register(adapter)
    monkeypatch.setattr("app.api.routes.providers.ProviderRegistry.default", lambda: registry)

    with TestClient(app) as client:
        response = client.get("/providers/models", params={"provider": "ollama"})
        assert response.status_code == 200
        payload = response.json()["providers"][0]
        assert payload["provider_name"] == "ollama"
        assert payload["models"] == ["capability-default"]


def test_run_flow_provider_synthesis_success_updates_fields_and_trace(monkeypatch) -> None:
    adapter = FakeProviderAdapter(
        generation_response=ProviderGenerationResponse(provider="ollama", model="llama3.1", output_text="provider run output")
    )
    registry = ProviderRegistry()
    registry.register(adapter)
    monkeypatch.setattr("core.synthesis.ProviderRegistry.default", lambda: registry)

    with TestClient(app) as client:
        create_run = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "ollama",
                "model": "llama3.1",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )
        assert create_run.status_code == 200
        run_payload = create_run.json()["run"]
        run_id = run_payload["id"]
        assert run_payload["synthesis_mode"] == "provider"
        assert run_payload["synthesis_status"] == "completed"
        assert run_payload["synthesis_error_summary"] is None
        assert run_payload["final_output"] == "provider run output"

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        trace_events = trace.json()
        event_types = [event["event_type"] for event in trace_events]
        trace_ids = [event["id"] for event in trace_events]
        assert trace_ids == sorted(trace_ids)
        assert "synthesis.started" in event_types
        assert "synthesis.completed" in event_types
        assert "synthesis.failed" not in event_types

        started_index = event_types.index("synthesis.started")
        completed_index = event_types.index("synthesis.completed")
        assert started_index < completed_index

        started_payload = json.loads(next(item for item in trace_events if item["event_type"] == "synthesis.started")["payload"])
        completed_payload = json.loads(next(item for item in trace_events if item["event_type"] == "synthesis.completed")["payload"])
        assert started_payload["provider"] == "ollama"
        assert started_payload["model"] == "llama3.1"
        assert completed_payload["mode"] == "provider"
        assert completed_payload["provider"] == "ollama"
