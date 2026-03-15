# Runtime Architecture (Synchronous Deterministic Research Slice)

## Components
- **API (`apps/api`)**: creates runs, executes runtime synchronously, persists run + traces, exposes run/trace routes.
- **Core (`packages/core`)**: deterministic planner, bounded multi-step executor, evidence aggregation, synthesis engine, runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions/runs/traces.
- **Skills (`packages/skills`)**: executable skill interfaces and built-in `filesystem`, `fetch`, and `web_search` skills.
- **Web (`apps/web`)**: dashboard and run detail UI showing synthesis mode, evidence summaries, and ordered trace events.

## Runtime flow
1. Client calls `POST /runs`.
2. API creates/attaches session and persists run (`pending` -> `running`).
3. `TaskRunner` records `run.started` and creates deterministic plan (`plan.created`).
4. `Executor` runs plan in order and emits tool lifecycle events:
   - `tool.requested`
   - `tool.started`
   - `tool.completed` or `tool.failed`
5. Research plans run `web_search` first, then bounded `fetch` of selected result URLs.
6. Executor aggregates compact evidence (search snippets, fetched page summaries, filesystem excerpts, notes/errors).
7. `SynthesisEngine` uses aggregated evidence:
   - provider synthesis when configured
   - deterministic fallback synthesis otherwise
8. Runtime emits terminal event (`run.completed` or `run.failed`) and API persists run summary fields and ordered traces.

## Planner behavior
- URL in task => direct `fetch` step.
- File/path/repo-reading intent => `filesystem` step.
- Research/comparison/pricing/docs lookup verbs => `web_search` then `fetch` from search results.
- Mixed file + research intent can produce `filesystem` + `web_search` + `fetch` sequence.
- Otherwise returns non-executable explanatory step.

## Guardrails and bounds
- **Filesystem**: workspace-root restriction, traversal prevention, max file size, UTF-8 text default.
- **Fetch**: HTTP/HTTPS only, timeout, response size cap, local/private target rejection.
- **Web search**: standard query validation, max result cap, timeout, URL normalization/deduplication, invalid/local target rejection.
- **Evidence/traces**: compact summaries only, no giant page-body dumps.

## Current limitations
- No model-driven tool planning/routing yet.
- No async worker queue/background runtime.
- Search providers intentionally small and environment-driven.
- No browser/shell execution or multi-agent orchestration.
