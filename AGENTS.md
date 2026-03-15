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
- Planner is deterministic and now supports URL/filepath heuristics plus research/comparison verbs.
- Runtime invokes built-in skills (`filesystem`, `fetch`, `web_search`) and persists ordered trace events.
- Research runs can execute bounded `web_search -> fetch` workflows and aggregate evidence.
- Runs persist status transitions (`pending`, `running`, `completed`, `failed`) and `final_output`.
- Run records include synthesis and compact execution/evidence summaries.

## Search configuration
- Optional `AGENTHUB_SEARCH_PROVIDER` (`searxng`, `duckduckgo`, `duckduckgo_instant`).
- Optional `AGENTHUB_SEARXNG_BASE_URL` for SearxNG deployment.
- Default behavior uses SearxNG when configured, otherwise DuckDuckGo Instant API fallback.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
