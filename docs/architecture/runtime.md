# Runtime Architecture (Synchronous Alpha)

## Components
- **API (`apps/api`)**: creates runs, executes runtime synchronously, persists run + traces, exposes run/trace routes.
- **Core (`packages/core`)**: deterministic planner, synchronous executor, task runner, structured runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions/runs/traces.
- **Skills (`packages/skills`)**: executable skill interfaces and built-in `filesystem` + `fetch` skills.
- **Web (`apps/web`)**: dashboard submission flow with run result panel.

## Runtime flow
1. Client calls `POST /runs`.
2. API creates/attaches session and persists run (`pending` -> `running`).
3. `TaskRunner` records `run.started` and creates a deterministic plan (`plan.created`).
4. `Executor` executes steps synchronously and emits tool lifecycle events:
   - `tool.requested`
   - `tool.started`
   - `tool.completed` or `tool.failed`
5. Runtime emits terminal event (`run.completed` or `run.failed`).
6. API persists ordered trace events and final run fields (`status`, `final_output`).

## Planner behavior
- URL in task => `fetch` step.
- File/path/repo-reading intent => `filesystem` step.
- Both may be planned in sequence.
- Otherwise returns minimal non-executable step with graceful insufficient-context messaging.

## Guardrails
- **Filesystem**: workspace-root restriction, traversal prevention, max file size, UTF-8 text default.
- **Fetch**: HTTP/HTTPS only, timeout, response size cap, local/private target rejection.

## Current limitations
- No autonomous model-driven planning/reasoning yet.
- No async worker queue/background runtime.
- No browser/shell execution or multi-agent orchestration.
