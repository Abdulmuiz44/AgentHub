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
- Runs persist through SQLite-backed sessions, runs, traces, approvals, providers, skill definitions, and per-skill config state.
- `POST /runs` queues work for the local in-process worker instead of executing the whole run inline.
- The worker lifecycle is bounded and local: queued -> running -> waiting_for_approval -> completed/failed/cancelled.
- Deterministic and model-assisted planning are both preserved under the worker path.
- Approval-gated steps pause the run, persist a checkpoint, and resume from stored state when approval is resolved.
- Cancellation is cooperative and processed safely for queued, running, and waiting runs.
- Run detail uses SSE to surface live progress without exposing hidden reasoning or secrets.
- Skill routing remains bounded: deterministic heuristics plus explicit `Use skill <name>` routing, with optional bounded model-assisted planning.
- Skill manifests can declare typed config requirements and planner-facing `capability_categories`.
- Non-secret config values persist in SQLite; secret-like fields persist environment variable names only.
- Runtime resolves secret bindings from process environment at test/execution time and fails safely when bindings or env values are missing.
- MCP support remains bounded to local stdio tool wrapping with safe env injection.

## Search configuration
- Optional `AGENTHUB_SEARCH_PROVIDER` (`searxng`, `duckduckgo`, `duckduckgo_instant`).
- Optional `AGENTHUB_SEARXNG_BASE_URL` for SearxNG deployment.
- Default behavior uses SearxNG when configured, otherwise DuckDuckGo Instant API fallback.

## Repo hygiene
- Temporary validation folders such as `.deps/`, `apps/api/.vendor/`, `.tmp/`, and `*.egg-info/` are ignored and should not be committed.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
