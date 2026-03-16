# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository currently includes:
- FastAPI backend with SQLite-backed sessions, runs, traces, approvals, provider metadata, and a persisted skill catalog
- Deterministic bounded execution with built-in native skills for filesystem, fetch, and web search
- Optional model-assisted planning with enabled/ready skill discovery, bounded validation, and deterministic fallback
- A local in-process run worker with queued, running, waiting-for-approval, completed, failed, and cancelled run states
- Persisted execution checkpoints that let approval-gated runs resume from stored plan and step state
- Local installable skill management for native and MCP stdio-backed skills
- Per-skill persisted configuration with readiness checks and environment-variable secret bindings
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
npm install
npm run dev
```

The dashboard uses `NEXT_PUBLIC_API_BASE` or defaults to `http://localhost:8000`.

## Run lifecycle

`POST /runs` now creates queued runs instead of blocking on full execution.

Current statuses:
- `pending`
- `queued`
- `running`
- `waiting_for_approval`
- `completed`
- `failed`
- `cancelled`

The API app starts one local in-process worker that:
- dequeues runs
- performs deterministic or model-assisted planning
- executes the shared bounded executor path
- pauses at approval boundaries
- resumes after approval resolution
- honors cooperative cancellation
- persists progress after each meaningful state change

Current lifecycle endpoints:
- `POST /runs`
- `GET /runs/{id}`
- `GET /runs/{id}/trace`
- `GET /runs/{id}/stream`
- `POST /runs/{id}/cancel`
- `POST /runs/{id}/approvals/{approval_id}/approve`
- `POST /runs/{id}/approvals/{approval_id}/deny`

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

Run detail pages now consume `GET /runs/{id}/stream` for compact server-sent progress updates.
The stream emits trace and run-status envelopes for:
- queueing
- planning
- tool execution
- approval pause/resume
- cancellation
- synthesis
- terminal completion/failure

## Skill platform

AgentHub has a real local skill catalog with two runtime types:
- `native_python`
- `mcp_stdio`

Catalog capabilities in this milestone:
- `GET /skills`
- `GET /skills/{name}`
- `GET /skills/{name}/config`
- `POST /skills/install`
- `POST /skills/{name}/config`
- `POST /skills/{name}/enable`
- `POST /skills/{name}/disable`
- `POST /skills/{name}/test`

## Current limits

- The worker is local and in-process only; there is no distributed job backend
- Cancellation is cooperative at safe step boundaries
- Approval resumption is checkpoint-based and local to the current process/database
- Model-assisted planning is a bounded planner input, not an autonomous loop
- The committed web lint config is present, but frontend lint validation may still require local npm dependency installation in environments where `eslint` is not yet installed
- Temp validation folders such as `.deps/` and `apps/api/.vendor/` are ignored and should not be committed
