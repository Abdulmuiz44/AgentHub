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
- Runs persist through SQLite-backed sessions, runs, traces, approvals, providers, and skill definitions.
- Planner routing remains deterministic and now supports explicit `Use skill <name>` routing for installed local skills.
- Runtime executes native Python skills and MCP stdio-backed skills through one shared execution contract.
- Skills are represented through a real local catalog with runtime type, manifest metadata, install source, and last test status.
- MCP support is bounded to local stdio tool wrapping (`initialize`, `tools/list`, `tools/call`, clean shutdown).
- Skills can be installed from a local manifest, enabled or disabled, and tested through API and UI.

## Search configuration
- Optional `AGENTHUB_SEARCH_PROVIDER` (`searxng`, `duckduckgo`, `duckduckgo_instant`).
- Optional `AGENTHUB_SEARXNG_BASE_URL` for SearxNG deployment.
- Default behavior uses SearxNG when configured, otherwise DuckDuckGo Instant API fallback.

## Repo hygiene
- Temporary validation folders such as `.deps/`, `apps/api/.vendor/`, and `*.egg-info/` are ignored and should not be committed.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
