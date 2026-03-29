# Runtime Architecture (Async Local Worker Slice)

## Components
- **API (`apps/api`)**: creates queued runs, exposes run/trace/stream/cancel/approval/change-review routes, and exposes typed skill catalog/install/config/enable/disable/test routes.
- **Run worker (`apps/api/app/services/worker.py`)**: single local in-process worker that dequeues runs, resumes incomplete queued work on startup, and executes one run at a time.
- **Runtime service (`apps/api/app/services/runtime.py`)**: owns queued-run creation, checkpoint persistence, planning, approval pause/resume, review-first proposal capture, apply/reject flows, synthesis finalization, and run serialization.
- **Change review service (`apps/api/app/services/change_review.py`)**: normalizes proposed file changes, generates compact unified diffs, validates workspace safety, and applies or rejects persisted change sets.
- **Core (`packages/core`)**: deterministic planner, bounded provider-assisted planning service, shared executor, evidence aggregation, synthesis engine, and runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions, runs, traces, approvals, providers, skill definitions, and review-first change artifacts.
- **Skills (`packages/skills`)**: shared manifest spec, native built-in skills, MCP stdio wrapper, and unified skill registry.
- **Web (`apps/web`)**: dashboard, live run detail UI, change review/apply/reject controls, and a practical skills management page.

## Run flow
1. `POST /runs` persists a queued run and an initial compact `execution_state` checkpoint.
2. The app-scoped worker dequeues the run outside the request path.
3. Planning runs inside the worker:
   - deterministic mode uses the heuristic planner
   - model-assisted mode performs one bounded provider planning call with local validation and deterministic fallback
4. The worker persists the selected plan and planning metadata to the run checkpoint.
5. The executor runs one bounded step at a time, updating checkpointed progress after each step.
6. If the next step requires approval, the worker creates or reuses an approval record, marks the run `waiting_for_approval`, emits pause traces, and exits cleanly.
7. Review-first mutation steps execute in proposal mode after approval, persist a change set plus per-file diff previews, and transition the run to `waiting_for_review`.
8. `POST /runs/{id}/apply` revalidates workspace safety and writes the proposed files only if the stored base state still matches.
9. `POST /runs/{id}/reject` preserves the change history and resolves the run without writing files.
10. `GET /runs/{id}/stream` exposes compact SSE envelopes for trace and run updates.

## Run lifecycle
Current persisted statuses:
- `pending`
- `queued`
- `running`
- `waiting_for_approval`
- `waiting_for_review`
- `completed`
- `failed`
- `cancelled`

Related persisted run metadata includes:
- `execution_mode`
- `mutation_apply_mode`
- `planning_source`
- `planning_summary`
- `fallback_reason`
- `pending_change_count`
- `review_status`
- `apply_summary`
- `reject_summary`
- `budget_config`
- `budget_usage_summary`
- `execution_state`
- `cancel_requested`

## Review-first change artifacts
A review-first mutation run stores:
- one change set record for the pending proposal batch
- one change-file record per affected path
- operation type (`create`, `overwrite`, `append` when supplied)
- pre-change checksum or file absence expectation
- post-change checksum
- compact before/after previews
- capped unified diff preview
- apply/reject/failure summaries

This keeps the review surface inspectable without storing large duplicate blobs in traces.

## Workspace safety checks
Apply is bounded and fails safely when:
- a proposed path escapes the configured workspace root
- a target is not a UTF-8 text file
- the current file content no longer matches the stored pre-change checksum or absence expectation

There is no three-way merge or git merge behavior in this milestone.

## Trace model
Important review-first lifecycle events now include:
- `run.queued`
- `run.started`
- `run.paused`
- `run.resumed`
- `approval.requested`
- `approval.resolved`
- `change.proposed`
- `change.review_pending`
- `change.apply_requested`
- `change.applied`
- `change.apply_failed`
- `change.rejected`
- `run.completed`
- `run.failed`

Trace payloads remain compact and do not store hidden reasoning, secrets, or full file bodies.

## Current limitations
- The worker is still single-process and local to the API app.
- Cancellation is boundary-based, not forceful termination of running subprocess trees.
- Review-first mutation capture depends on cooperative mutation-capable local skills returning normalized proposed file changes.
- Apply is all-or-fail and text-only; there is no partial apply, merge, or remote VCS integration in this slice.
- The committed web lint config is present, but lint validation still depends on local npm dependency availability.
