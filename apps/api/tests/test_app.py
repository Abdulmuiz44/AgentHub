import time

from fastapi.testclient import TestClient

from app.main import app


def wait_for_terminal(client: TestClient, run_id: int, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    worker = client.app.state.run_worker
    while time.time() < deadline:
        worker.wait_for_idle(timeout=0.2)
        response = client.get(f"/runs/{run_id}")
        assert response.status_code == 200
        run = response.json()
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.05)
    raise AssertionError(f"Run {run_id} did not reach a terminal state")


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
                "execution_mode": "deterministic",
            },
        )
        assert create_run.status_code == 200
        run_payload = create_run.json()
        run_id = run_payload["run"]["id"]
        assert run_payload["run"]["status"] == "queued"
        assert run_payload["run"]["execution_mode"] == "deterministic"
        assert "planning_source" in run_payload["run"]
        assert "budget_config" in run_payload["run"]

        get_run = client.get(f"/runs/{run_id}")
        assert get_run.status_code == 200

        final = wait_for_terminal(client, run_id)
        assert final["status"] in {"completed", "failed", "cancelled"}

        trace = client.get(f"/runs/{run_id}/trace")
        assert trace.status_code == 200
        event_types = {item["event_type"] for item in trace.json()}
        assert "run.queued" in event_types
        assert "planning.completed" in event_types

        invalid_mode = client.post(
            "/runs",
            json={
                "task": "Read README.md",
                "provider": "builtin",
                "model": "deterministic",
                "execution_mode": "bad-mode",
            },
        )
        assert invalid_mode.status_code == 422

        providers = client.get("/providers")
        assert providers.status_code == 200
        provider_names = {item["provider"]["name"] for item in providers.json()}
        assert {"ollama", "openai"}.issubset(provider_names)

        skills = client.get("/skills")
        assert skills.status_code == 200
        skill_names = {item["name"] for item in skills.json()}
        assert {"filesystem", "fetch", "web_search"}.issubset(skill_names)
