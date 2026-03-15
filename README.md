# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository now includes a first real execution slice:
- FastAPI backend with SQLite-backed sessions/runs/traces
- Synchronous runtime loop (planner + executor + tracing)
- Built-in executable skills: read-only filesystem + HTTP fetch
- Next.js dashboard showing run status, output, and trace preview

## Repository layout

- `apps/api` — FastAPI backend
- `apps/web` — Next.js frontend
- `packages/*` — shared Python runtime, memory, provider, and skill packages
- `docs/` — product and architecture notes

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

## Supported task types (current milestone)

- List files in a directory (`filesystem:list_directory`)
- Read a local UTF-8 file (`filesystem:read_text_file`)
- Fetch and read text from HTTP/HTTPS URLs (`fetch:fetch_url`)

## Current limitations

- Deterministic heuristics planner only (no autonomous model-driven planning)
- Synchronous in-request execution only
- No browser/shell/voice/OCR/multi-agent orchestration
