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
                "task": "Summarize repo layout",
                "provider": "ollama",
                "model": "llama3.1",
                "session_id": session["id"],
                "enabled_skills": ["filesystem"],
            },
        )
        assert create_run.status_code == 200
        run_payload = create_run.json()
        run_id = run_payload["run"]["id"]

        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        event_types = {item["event_type"] for item in trace.json()}
        assert "run.started" in event_types
        assert "plan.created" in event_types

        providers = client.get("/providers")
        assert providers.status_code == 200
        provider_names = {item["name"] for item in providers.json()}
        assert {"ollama", "openai"}.issubset(provider_names)

        skills = client.get("/skills")
        assert skills.status_code == 200
        skill_names = {item["name"] for item in skills.json()}
        assert "filesystem" in skill_names
