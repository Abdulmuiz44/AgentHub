# Runtime Architecture (Async Local Worker Slice)

## Components
- **API (`apps/api`)**: creates queued runs, exposes run/trace/stream/cancel/approval routes, and exposes typed skill catalog/install/config/enable/disable/test routes.
- **Run worker (`apps/api/app/services/worker.py`)**: single local in-process worker that dequeues runs, resumes incomplete queued work on startup, and executes one run at a time.
- **Runtime service (`apps/api/app/services/runtime.py`)**: owns queued-run creation, checkpoint persistence, planning, approval pause/resume, cancellation handling, synthesis finalization, and run serialization.
- **Core (`packages/core`)**: deterministic planner, bounded provider-assisted planning service, shared executor, evidence aggregation, synthesis engine, and runtime contracts.
- **Skill catalog service (`apps/api/app/services/skills.py`)**: seeds built-ins, persists local skill definitions, validates readiness, exposes planner-facing eligible skills, tests skills, and builds runtime registries.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions, runs, traces, approvals, providers, and skill definitions/config state.
- **Skills (`packages/skills`)**: shared manifest spec, native built-in skills, MCP stdio wrapper, and unified skill registry.
- **Web (`apps/web`)**: dashboard, live run detail UI, and a practical skills management page.

## Run flow
1. `POST /runs` persists a queued run and an initial compact `execution_state` checkpoint.
2. The app-scoped worker dequeues the run outside the request path.
3. Planning runs inside the worker:
   - deterministic mode uses the heuristic planner
   - model-assisted mode performs one bounded provider planning call with local validation and deterministic fallback
4. The worker persists the selected plan and planning metadata to the run checkpoint.
5. The executor runs one bounded step at a time, updating checkpointed progress after each step.
6. If the next step requires approval, the worker creates or reuses an approval record, marks the run `waiting_for_approval`, emits pause traces, and exits cleanly.
7. Approval resolution re-enqueues the run; the worker reloads the checkpoint and resumes from the stored step index.
8. If cancellation is requested, the worker stops at the next safe boundary and marks the run `cancelled`.
9. After all steps complete, the runtime performs synthesis and persists the terminal run state.
10. `GET /runs/{id}/stream` exposes compact SSE envelopes for trace and run updates.

## Run lifecycle
Current persisted statuses:
- `pending`
- `queued`
- `running`
- `waiting_for_approval`
- `completed`
- `failed`
- `cancelled`

Related persisted run metadata includes:
- `execution_mode`
- `planning_source`
- `planning_summary`
- `fallback_reason`
- `budget_config`
- `budget_usage_summary`
- `execution_state`
- `cancel_requested`

## Execution checkpoint model
`execution_state` is a compact JSON checkpoint containing:
- enabled skills for the run
- bounded budget config
- current plan
- current step index
- accumulated step results
- evidence bundle summary state
- working search results for fetch-from-search continuation
- planning source/summary/fallback metadata
- budget usage summary
- pending approval id if paused
- failure context if present

This state is sufficient for:
- approval pause/resume
- cancellation at safe boundaries
- restart recovery for queued/running runs that can be safely re-queued

## Approvals
Approval support is now first-class in the worker lifecycle.

When a selected step is approval-gated:
- an approval record is created or reused
- the run status becomes `waiting_for_approval`
- the checkpoint stores the pending approval id
- `approval.requested` and `run.paused` traces are emitted

When approval is resolved:
- `approval.resolved` is traced
- approved runs emit `run.resumed` and continue from the stored step index
- denied runs terminate clearly with `run.failed`

## Cancellation
Cancellation remains cooperative and bounded.

Current behavior:
- queued runs can be cancelled before execution
- waiting runs can be cancelled immediately
- running runs mark `cancel_requested` and stop at the next safe boundary
- cancellation emits `run.cancel_requested` and `run.cancelled` traces
- no subprocess force-kill logic is introduced in this slice

## Live progress streaming
`GET /runs/{id}/stream` emits compact SSE envelopes of two kinds:
- `trace`: ordered trace event records
- `run`: current serialized run state when status changes

The run detail page uses this stream to keep queued/running/waiting/completed/failed/cancelled views current without polling-heavy UI code.

## Trace model
Important async lifecycle events now include:
- `run.queued`
- `run.started`
- `run.paused`
- `run.resumed`
- `run.cancel_requested`
- `run.cancelled`
- `planning.started`
- `planning.completed`
- `planning.fallback`
- `approval.requested`
- `approval.resolved`
- `tool.started`
- `tool.completed`
- `tool.failed`
- `synthesis.started`
- `synthesis.completed`
- `run.completed`
- `run.failed`

Trace payloads remain compact and do not store hidden reasoning, secrets, or large provider dumps.

## Current limitations
- The worker is still single-process and local to the API app.
- Cancellation is boundary-based, not forceful termination of running subprocess trees.
- Restart handling re-queues queued/running runs, but does not attempt distributed locking or exactly-once execution semantics.
- Approval routing is step-boundary based; there is no broader policy engine in this milestone.
- The committed web lint config is present, but lint validation still depends on local npm dependency availability.
