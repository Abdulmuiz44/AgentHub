import json

from fastapi.testclient import TestClient

from app.main import app
from models.base import ProviderCapability
from models.registry import ProviderRegistry


class FakeAdapter:
    def __init__(self, name: str, models: list[str], output: str = "mocked synthesis") -> None:
        self._capability = ProviderCapability(
            name=name,
            display_name=name.title(),
            models=models,
            supports_streaming=True,
        )
        self.output = output

    @property
    def capability(self) -> ProviderCapability:
        return self._capability

    def generate(self, prompt: str, model: str, **kwargs) -> str:
        _ = (prompt, model, kwargs)
        return self.output


class FakeRegistry:
    def __init__(self, adapters: dict[str, FakeAdapter]) -> None:
        self._adapters = adapters

    def get(self, name: str):
        return self._adapters.get(name)

    def capabilities(self):
        return [adapter.capability for adapter in self._adapters.values()]


def test_provider_registry_behavior() -> None:
    registry = ProviderRegistry()
    first = FakeAdapter(name="demo", models=["m1"])
    second = FakeAdapter(name="demo", models=["m2"])

    registry.register(first)
    assert registry.get("demo") is first
    assert [item.name for item in registry.capabilities()] == ["demo"]

    registry.register(second)
    assert registry.get("demo") is second
    assert registry.get("missing") is None
    assert registry.capabilities()[0].models == ["m2"]


def test_synthesis_fallback_when_provider_config_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.services.runs.settings.openai_api_key", None)

    with TestClient(app) as client:
        create_run = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )

    assert create_run.status_code == 200
    payload = create_run.json()
    metadata = payload["execution_metadata"]
    assert metadata["synthesis_enabled"] is True
    assert metadata["synthesis_status"] == "skipped"
    assert metadata["synthesis_output"] is None

    event_types = [item["event_type"] for item in payload["trace_events"]]
    assert "synthesis.skipped" in event_types


def test_synthesis_success_with_mocked_provider(monkeypatch) -> None:
    fake = FakeAdapter(name="openai", models=["gpt-4o-mini"], output="final synthesized answer")
    monkeypatch.setattr("app.services.runs.settings.openai_api_key", "test-key")
    monkeypatch.setattr("app.services.runs.ProviderRegistry.default", lambda: FakeRegistry({"openai": fake}))

    with TestClient(app) as client:
        create_run = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )

    assert create_run.status_code == 200
    payload = create_run.json()
    metadata = payload["execution_metadata"]
    assert metadata["synthesis_status"] == "completed"
    assert metadata["synthesis_output"] == "final synthesized answer"

    event_types = [item["event_type"] for item in payload["trace_events"]]
    assert "synthesis.requested" in event_types
    assert "synthesis.completed" in event_types


def test_provider_catalog_routes(monkeypatch) -> None:
    monkeypatch.setattr("app.api.routes.catalog.settings.openai_api_key", "key")
    monkeypatch.setattr("app.api.routes.catalog.settings.ollama_base_url", "http://localhost:11434")

    with TestClient(app) as client:
        providers = client.get("/providers")
        assert providers.status_code == 200
        assert {item["name"] for item in providers.json()} >= {"openai", "ollama"}

        models = client.get("/providers/models")
        assert models.status_code == 200
        assert any(item["provider"] == "openai" for item in models.json())

        openai_models = client.get("/providers/models", params={"provider": "openai"})
        assert openai_models.status_code == 200
        assert len(openai_models.json()) == 1

        health = client.get("/providers/health-check")
        assert health.status_code == 200
        statuses = {item["provider"]: item["status"] for item in health.json()}
        assert statuses["openai"] == "ready"
        assert statuses["ollama"] == "ready"


def test_run_execution_metadata_includes_synthesis_fields(monkeypatch) -> None:
    monkeypatch.setattr("app.services.runs.settings.openai_api_key", None)

    with TestClient(app) as client:
        response = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )

    assert response.status_code == 200
    metadata = response.json()["execution_metadata"]
    assert set(["synthesis_enabled", "synthesis_provider", "synthesis_model", "synthesis_status", "synthesis_output"]).issubset(
        metadata.keys()
    )


def test_trace_ordering_includes_synthesis_events(monkeypatch) -> None:
    fake = FakeAdapter(name="openai", models=["gpt-4o-mini"], output="ordered synthesis")
    monkeypatch.setattr("app.services.runs.settings.openai_api_key", "test-key")
    monkeypatch.setattr("app.services.runs.ProviderRegistry.default", lambda: FakeRegistry({"openai": fake}))

    with TestClient(app) as client:
        response = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "enabled_skills": ["filesystem"],
                "execute_now": True,
            },
        )
        assert response.status_code == 200
        run_id = response.json()["run"]["id"]

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200

    event_types = [item["event_type"] for item in trace.json()]
    assert event_types[0] == "run.started"
    assert event_types[-1] in {"run.completed", "run.failed"}
    assert event_types.index("synthesis.requested") < event_types.index("synthesis.completed") < len(event_types) - 1

    synthesis_event = next(item for item in trace.json() if item["event_type"] == "synthesis.completed")
    synthesis_payload = json.loads(synthesis_event["payload"])
    assert synthesis_payload["provider"] == "openai"
