# AgentHub v0.1 Foundation

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository contains the v0.1 monorepo foundation:
- FastAPI backend scaffold with SQLite-backed sessions/runs/traces
- Next.js dashboard scaffold wired to backend run creation
- Typed runtime contracts
- Provider and skill registries
- Read-only filesystem skill slice

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

### Web

```bash
cd apps/web
npm install
npm run dev
```

The dashboard uses `NEXT_PUBLIC_API_BASE` or defaults to `http://localhost:8000`.
