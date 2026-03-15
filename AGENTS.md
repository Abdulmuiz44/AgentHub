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
- Planner is deterministic and supports URL/filepath heuristics only.
- Runtime invokes built-in skills (`filesystem`, `fetch`) and persists ordered trace events.
- Optional synthesis can run after deterministic execution when provider config exists.
- If synthesis provider config is missing, runtime falls back to deterministic output and emits `synthesis.skipped`.
- Runs persist status transitions (`pending`, `running`, `completed`, `failed`) and `final_output`.
- Provider catalog endpoints include `/providers`, `/providers/models`, `/providers/health-check`.

## Environment configuration
- OpenAI synthesis: `AGENTHUB_OPENAI_API_KEY` (required), `AGENTHUB_OPENAI_BASE_URL` (optional), `AGENTHUB_OPENAI_DEFAULT_MODEL`.
- Ollama synthesis: `AGENTHUB_OLLAMA_BASE_URL` (required), `AGENTHUB_OLLAMA_DEFAULT_MODEL`.

## Definition of done (small tasks)
- API starts and health route responds.
- Touched endpoints have persistence-backed behavior.
- Tests/checks run for touched areas where environment allows.
- Docs reflect real commands and structure.
