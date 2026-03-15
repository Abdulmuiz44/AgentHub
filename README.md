# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository includes a real execution slice:
- FastAPI backend with SQLite-backed sessions/runs/traces
- Synchronous deterministic runtime loop (planner + executor + tracing)
- Built-in executable skills: read-only filesystem + HTTP fetch
- Optional provider synthesis pass after deterministic execution
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

## Provider synthesis configuration (optional)

Runtime execution is always deterministic first. A synthesis step is optional and only runs when a non-`builtin` provider is requested and configured.

- OpenAI requires `AGENTHUB_OPENAI_API_KEY`
- Ollama requires `AGENTHUB_OLLAMA_BASE_URL`
- Optional defaults:
  - `AGENTHUB_OPENAI_DEFAULT_MODEL` (default: `gpt-4o-mini`)
  - `AGENTHUB_OLLAMA_DEFAULT_MODEL` (default: `llama3.1`)

If provider configuration is missing, the run falls back to deterministic output and records `synthesis.skipped` trace metadata.

## Provider catalog endpoints

- `GET /providers`
- `GET /providers/models`
- `GET /providers/health-check`

## Supported task types (current milestone)

- List files in a directory (`filesystem:list_directory`)
- Read a local UTF-8 file (`filesystem:read_text_file`)
- Fetch and read text from HTTP/HTTPS URLs (`fetch:fetch_url`)

## Current limitations

- Deterministic heuristics planner only (no autonomous model-driven planning)
- Synchronous in-request execution only
- No browser/shell/voice/OCR/multi-agent orchestration
