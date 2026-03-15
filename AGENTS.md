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
- `POST /runs` persists a queued run and returns immediately.
- The API starts a bounded in-process worker for local async execution.
- Run lifecycle now includes `pending`, `queued`, `running`, `waiting_for_approval`, `completed`, `failed`, and `cancelled`.
- Runs persist compact execution checkpoints (`plan`, current step index, step results, evidence summary, pending approval refs).
- Approval-required steps create approval records, pause the run, and resume after approval grant.
- Approval denial fails the run with clear trace output.
- `POST /runs/{id}/cancel` cancels queued/waiting runs immediately and requests cooperative cancellation for running runs.
- `GET /runs/{id}/stream` streams live trace/status updates for the run detail page.

## Search configuration
- Optional `AGENTHUB_SEARCH_PROVIDER` (`searxng`, `duckduckgo`, `duckduckgo_instant`).
- Optional `AGENTHUB_SEARXNG_BASE_URL` for SearxNG deployment.
- Default behavior uses SearxNG when configured, otherwise DuckDuckGo Instant API fallback.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
