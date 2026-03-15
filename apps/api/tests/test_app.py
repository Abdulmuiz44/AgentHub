from fastapi.testclient import TestClient

from app.main import app


def test_health_route() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sessions_runs_and_catalog_flow() -> None:
    with TestClient(app) as client:
        create_session = client.post("/sessions", json={"name": "demo"})
        assert create_session.status_code == 200
        session = create_session.json()

        list_sessions = client.get("/sessions")
        assert list_sessions.status_code == 200
        assert any(item["id"] == session["id"] for item in list_sessions.json())

        create_run = client.post(
            "/runs",
            json={
                "task": "Summarize README.md",
                "provider": "builtin",
                "model": "deterministic",
                "session_id": session["id"],
                "enabled_skills": ["filesystem"],
            },
        )
        assert create_run.status_code == 200
        run_payload = create_run.json()
        run_id = run_payload["run"]["id"]
        assert run_payload["run"]["status"] in {"completed", "failed"}

        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200
        get_run_payload = get_run.json()
        assert "synthesis_mode" in get_run_payload
        assert "output" in get_run_payload

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        event_types = {item["event_type"] for item in trace.json()}
        assert "run.started" in event_types
        assert "plan.created" in event_types

        providers = client.get("/providers")
        assert providers.status_code == 200
        provider_names = {item["provider"]["name"] for item in providers.json()}
        assert {"ollama", "openai"}.issubset(provider_names)

        provider_models = client.get("/providers/models")
        assert provider_models.status_code == 200
        provider_models_payload = provider_models.json()
        assert "providers" in provider_models_payload
        ollama_models = next(item for item in provider_models_payload["providers"] if item["provider_name"] == "ollama")
        assert "configuration_status" in ollama_models
        assert "is_configured" in ollama_models
        assert "models" in ollama_models
        assert "message" in ollama_models

        ollama_health = client.post("/providers/health-check", json={"provider": "ollama"})
        assert ollama_health.status_code == 200
        ollama_health_payload = ollama_health.json()
        assert "configuration_status" in ollama_health_payload
        assert isinstance(ollama_health_payload["healthy"], bool)
        assert isinstance(ollama_health_payload["message"], str)

        unknown_provider_health = client.post("/providers/health-check", json={"provider": "missing"})
        assert unknown_provider_health.status_code == 404
        assert unknown_provider_health.json()["detail"] == "Provider not found"

        skills = client.get("/skills")
        assert skills.status_code == 200
        skill_names = {item["name"] for item in skills.json()}
        assert {"filesystem", "fetch", "web_search"}.issubset(skill_names)
