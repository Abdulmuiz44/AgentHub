# AgentHub Contributor Guide

## Repo layout
- `apps/api`: FastAPI service
- `apps/web`: Next.js dashboard
- `packages`: shared runtime, memory, models, and skills packages
- `docs`: roadmap and architecture docs

## Run commands
- API: `cd apps/api && uv sync && uv run uvicorn app.main:app --reload --port 8000`
- API tests: `cd apps/api && uv run pytest`
- Web: `cd apps/web && npm install && npm run dev`
- Web lint: `cd apps/web && npm run lint`

## Coding rules
- Prefer explicit typing and small modules.
- Use environment-driven config for app behavior.
- Keep persistence real (SQLite) for foundation endpoints.

## Scope control
- Deliver only the requested slice.
- Avoid speculative abstractions and advanced product surface.

## Runtime slice (current alpha)
- `POST /runs` executes synchronously by default (`execute_now=true`).
- Planner/executor remain deterministic (URL/filepath heuristics + built-in skills).
- Runtime includes a synthesis stage with provider path and deterministic fallback path.
- Provider endpoints available: `/providers`, `/providers/models`, `/providers/health-check`.
- Runs persist status transitions (`pending`, `running`, `completed`, `failed`), `final_output`, and synthesis metadata fields (`synthesis_mode`, `synthesis_status`, `synthesis_error_summary`).
- Web run detail route `/runs/[id]` shows run summary + trace timeline.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
