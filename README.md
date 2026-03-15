# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository now includes an asynchronous deterministic runtime slice:
- FastAPI backend with SQLite-backed sessions, runs, traces, and approvals
- In-process worker queue for bounded local async execution
- Persisted resumable execution checkpoints for queued, running, and approval-paused runs
- Built-in executable skills: read-only filesystem, HTTP fetch, and web search
- Deterministic research workflow: `web_search -> fetch -> evidence aggregation -> synthesis`
- SSE run progress streaming plus dashboard and live run detail UI with approval/cancel controls

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

## Async runtime lifecycle

Run statuses for this milestone:
- `pending`
- `queued`
- `running`
- `waiting_for_approval`
- `completed`
- `failed`
- `cancelled`

Key behavior:
- `POST /runs` returns quickly with a queued run and run id.
- The API process starts a small in-process worker on startup.
- Runs persist compact execution checkpoints (`plan`, `current_step_index`, `step_results`, `evidence`, pending approval refs).
- Approval-required steps pause execution, persist state, and resume after approval.
- `POST /runs/{id}/cancel` cancels queued/waiting runs immediately and requests cooperative cancellation for running runs.
- `GET /runs/{id}/stream` exposes an SSE feed of trace/status updates for the run detail page.

## Search configuration

- `AGENTHUB_SEARCH_PROVIDER` (optional): `searxng`, `duckduckgo`, or `duckduckgo_instant`.
- `AGENTHUB_SEARXNG_BASE_URL` (optional): required when provider is `searxng`.

Default behavior:
- if `AGENTHUB_SEARXNG_BASE_URL` is set, use SearxNG
- otherwise use DuckDuckGo Instant Answer API fallback

## OpenAI provider environment variables

OpenAI configuration follows an `AGENTHUB_`-first policy with optional backward-compatible fallbacks:

- `AGENTHUB_OPENAI_API_KEY` (preferred)
  - Fallback: `OPENAI_API_KEY`
- `AGENTHUB_OPENAI_BASE_URL` (preferred, defaults to `https://api.openai.com/v1`)
  - Fallback: `OPENAI_BASE_URL`
- `AGENTHUB_OPENAI_TIMEOUT_SECONDS` (preferred, defaults to `30.0`)
  - Fallback: `OPENAI_TIMEOUT_SECONDS`

## Supported task types (current milestone)

- List files in a directory (`filesystem:list_directory`)
- Read a local UTF-8 file (`filesystem:read_text_file`)
- Fetch and read text from HTTP/HTTPS URLs (`fetch:fetch_url`)
- Research/find/compare/look-up tasks (`web_search` + bounded `fetch`)
- Approval-paused execution for risky steps that declare non-read-only capabilities

## Current limits

- Deterministic, heuristic planner only (no provider tool routing)
- Single-process in-memory worker only; no external queue or distributed execution
- Resume is checkpoint-based and can replay the current step after a process crash if it was interrupted mid-step
- Search/fetch are bounded by max result counts, fetch limits, timeout, and content-size caps
- Trace payloads store compact summaries/previews instead of full document bodies
- No browser/shell/voice/OCR/multi-agent orchestration
