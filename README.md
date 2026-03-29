# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository currently includes:
- FastAPI backend with SQLite-backed sessions, runs, traces, approvals, provider metadata, skill catalog metadata, per-skill config state, and persisted review-first change artifacts
- Deterministic bounded execution with built-in native skills for filesystem, fetch, and web search
- Optional model-assisted planning with enabled/ready skill discovery, bounded validation, and deterministic fallback
- A local in-process run worker with queued, running, waiting-for-approval, waiting-for-review, completed, failed, and cancelled run states
- Persisted execution checkpoints that let approval-gated runs resume from stored plan and step state
- Local installable skill management for native and MCP stdio-backed skills
- Review-first mutation handling with persisted change sets, diff previews, and apply/reject controls
- Next.js dashboard, live run detail page, and a simple skills management view

## Repository layout

- `apps/api` - FastAPI backend
- `apps/web` - Next.js frontend
- `packages/*` - shared Python runtime, memory, provider, and skill packages
- `docs/` - product and architecture notes

## Quick start

### API

```bash
cd apps/api
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### API tests

```bash
cd apps/api
uv run pytest
```

### Web

```bash
cd apps/web
pnpm install
npm run dev
```

The dashboard uses `NEXT_PUBLIC_API_BASE` or defaults to `http://localhost:8000`.

## Run lifecycle

`POST /runs` creates queued runs instead of blocking on full execution.

Current statuses:
- `pending`
- `queued`
- `running`
- `waiting_for_approval`
- `waiting_for_review`
- `completed`
- `failed`
- `cancelled`

Current lifecycle endpoints:
- `POST /runs`
- `GET /runs/{id}`
- `GET /runs/{id}/trace`
- `GET /runs/{id}/stream`
- `GET /runs/{id}/changes`
- `POST /runs/{id}/apply`
- `POST /runs/{id}/reject`
- `POST /runs/{id}/cancel`
- `POST /runs/{id}/approvals/{approval_id}/approve`
- `POST /runs/{id}/approvals/{approval_id}/deny`

## Mutation apply modes

Runs support two mutation apply modes:
- `direct_apply`
- `review_first`

`direct_apply` preserves current behavior.

`review_first` keeps mutation-capable steps from applying workspace text changes immediately. Instead, the runtime:
- captures proposed file changes as persisted change-set artifacts
- stores compact diff previews and checksums
- transitions the run to `waiting_for_review` when changes are proposed
- requires explicit apply or reject before files are written

Apply safety checks verify:
- workspace-root confinement
- UTF-8 text-only apply
- stale-base detection using the stored pre-change checksum or file absence expectation

## Execution modes

Runs support two execution modes:
- `deterministic`
- `model_assisted`

Deterministic mode remains the default.

Model-assisted mode stays bounded:
- one provider planning call
- enabled, ready skills only
- local validation before execution
- compact decision summaries only
- deterministic fallback on unavailable or invalid provider planning
- no hidden reasoning storage

## Live progress

Run detail pages consume `GET /runs/{id}/stream` for compact server-sent progress updates.
The stream emits trace and run-status envelopes for:
- queueing
- planning
- tool execution
- approval pause/resume
- review-pending transitions
- apply/reject outcomes
- cancellation
- synthesis
- terminal completion/failure

## Current limits

- The worker is local and in-process only; there is no distributed job backend
- Cancellation is cooperative at safe step boundaries
- Review-first mutation capture is designed for cooperative mutation-capable local skills; it is not a full VCS or merge engine
- Apply/reject is text-only and all-or-fail; there is no three-way merge logic
- Frontend lint/typecheck assume `pnpm install` has been run in `apps/web` so local lint dependencies are available
- Temp validation folders such as `.deps/` and `apps/api/.vendor/` are ignored and should not be committed



