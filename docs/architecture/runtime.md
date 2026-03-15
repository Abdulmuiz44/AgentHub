# Runtime Architecture (Synchronous Alpha)

## Components
- **API (`apps/api`)**: creates runs, executes runtime synchronously, persists run + traces, exposes run/trace routes and provider catalog routes.
- **Core (`packages/core`)**: deterministic planner, synchronous executor, task runner, structured runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions/runs/traces.
- **Models (`packages/models`)**: provider registry + adapters used by optional synthesis.
- **Skills (`packages/skills`)**: executable skill interfaces and built-in `filesystem` + `fetch` skills.
- **Web (`apps/web`)**: dashboard submission flow with run result panel and trace preview.

## Runtime flow
1. Client calls `POST /runs`.
2. API creates/attaches session and persists run (`pending` -> `running`).
3. `TaskRunner` records `run.started` and creates a deterministic plan (`plan.created`).
4. `Executor` executes steps synchronously and emits tool lifecycle events:
   - `tool.requested`
   - `tool.started`
   - `tool.completed` or `tool.failed`
5. API optionally attempts provider synthesis:
   - emits `synthesis.requested` + `synthesis.completed` on success
   - emits `synthesis.skipped` when provider config is missing or provider is `builtin`
   - emits `synthesis.failed` if adapter synthesis raises
6. API emits terminal event (`run.completed` or `run.failed`) and persists ordered trace events and final run fields (`status`, `final_output`).
7. `POST /runs` includes `execution_metadata` with synthesis fields for run detail UX.

## Planner behavior
- URL in task => `fetch` step.
- File/path/repo-reading intent => `filesystem` step.
- Both may be planned in sequence.
- Otherwise returns minimal non-executable step with graceful insufficient-context messaging.

## Provider endpoints
- `GET /providers`: adapter capabilities.
- `GET /providers/models`: model lists (optionally filtered by provider).
- `GET /providers/health-check`: configuration readiness (`ready` / `missing_config`) for OpenAI/Ollama.

## Environment-driven synthesis config
- `AGENTHUB_OPENAI_API_KEY` is required for OpenAI synthesis.
- `AGENTHUB_OLLAMA_BASE_URL` is required for Ollama synthesis.
- Default model env vars are optional (`AGENTHUB_OPENAI_DEFAULT_MODEL`, `AGENTHUB_OLLAMA_DEFAULT_MODEL`).
- Missing config always falls back to deterministic executor output.

## Guardrails
- **Filesystem**: workspace-root restriction, traversal prevention, max file size, UTF-8 text default.
- **Fetch**: HTTP/HTTPS only, timeout, response size cap, local/private target rejection.

## Current limitations
- No autonomous model-driven planning/reasoning yet.
- No async worker queue/background runtime.
- No browser/shell execution or multi-agent orchestration.
