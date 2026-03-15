# Runtime Architecture (Asynchronous Deterministic Local Worker Slice)

## Components
- **API (`apps/api`)**: creates runs, exposes lifecycle routes, approval decisions, cancellation, trace retrieval, and SSE progress streaming.
- **Worker (`apps/api/app/services/worker.py`)**: bounded in-process queue consumer that executes one run at a time by default.
- **Runtime (`apps/api/app/services/runtime.py`)**: planner + executor + approval + synthesis orchestration with persisted checkpoints.
- **Core (`packages/core`)**: deterministic planner, resumable bounded executor, evidence aggregation, synthesis engine, runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions, runs, traces, and approvals.
- **Skills (`packages/skills`)**: executable skill interfaces and built-in `filesystem`, `fetch`, and `web_search` skills.
- **Web (`apps/web`)**: dashboard and live run detail UI showing status, checkpoint state, approvals, cancellation, and ordered trace events.

## Runtime flow
1. Client calls `POST /runs`.
2. API persists a queued run, stores provider/model/requested skills, emits `run.queued`, and submits the run id to the in-process worker.
3. Worker picks up the run, loads or reconstructs the persisted checkpoint, transitions the run to `running`, and emits `run.started` or `run.resumed`.
4. Runtime creates a deterministic plan once, persists it into `execution_state`, and emits `plan.created`.
5. Executor processes plan steps in order, persisting progress after each step and emitting tool lifecycle events:
   - `tool.requested`
   - `tool.started`
   - `tool.completed` or `tool.failed`
6. If a step requires approval, runtime creates an approval record, persists the checkpoint, sets the run to `waiting_for_approval`, and emits:
   - `approval.requested`
   - `run.paused`
7. Approval resolution is persisted through `POST /approvals/{id}/decision`:
   - approval grant => run re-queued and later resumed from the checkpoint
   - approval denial => run failed immediately with `approval.resolved` and `run.failed`
8. Before each safe boundary the runtime checks for cancel requests:
   - queued/waiting runs cancel immediately
   - running runs cancel cooperatively before the next step or synthesis boundary
9. After steps finish, runtime emits `synthesis.started`, performs provider-backed synthesis or deterministic fallback, emits `synthesis.completed`, and then emits `run.completed` or `run.failed`.
10. `GET /runs/{id}/stream` polls persisted traces/status and sends compact SSE updates to the run detail page.

## Persisted checkpoint shape
`run.execution_state` stores compact resumable data:
- `plan`
- `current_step_index`
- `step_results`
- `evidence`
- `working_search_results`
- `pending_approval_id`
- `pending_approval_step_id`
- `pending_approval_reason`
- `synthesis`
- `failure_context`
- `change_summary`

This avoids duplicating full raw tool outputs while keeping enough state to resume and debug execution.

## Guardrails and bounds
- **Worker**: single-process, bounded concurrency, clean startup/shutdown from the FastAPI lifespan.
- **Filesystem**: workspace-root restriction, traversal prevention, max file size, UTF-8 text default.
- **Fetch**: HTTP/HTTPS only, timeout, response size cap, local/private target rejection.
- **Web search**: query validation, max result cap, timeout, URL normalization/deduplication, invalid/local target rejection.
- **Evidence/traces**: compact summaries only, no giant page-body dumps or secret streaming.
- **Cancellation**: cooperative only, no force-killing subprocess trees.

## Current limitations
- No external queue, distributed worker pool, or multi-process coordination.
- Mid-step crash recovery is checkpoint-based and may replay the in-flight step after restart.
- The planner remains deterministic and heuristic-driven; models still do not choose tools.
- Approval flow is wired for steps that declare risky/non-read-only capabilities; built-in default skills remain read-only.
- SSE currently polls persisted traces/status rather than pushing from a dedicated pub/sub bus.
