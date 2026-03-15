# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository includes an execution slice where **deterministic planning + deterministic tool execution remain the source of truth**. Model providers are used only in a post-execution synthesis stage.

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

## Runtime behavior (current milestone)

- `POST /runs` executes synchronously by default with `execute_now=true`.
- Planner behavior is deterministic (URL/filepath heuristics only).
- Executor behavior is deterministic and uses built-in skills (`filesystem`, `fetch`).
- A synthesis stage runs after execution:
  - **Provider path** when `provider`/`model` point to a configured model provider.
  - **Deterministic fallback path** (`synthesis_mode="deterministic_fallback"`) when provider/model are unavailable, builtin, deterministic, or erroring.
- Run records persist `status`, `final_output`, `synthesis_mode`, `synthesis_status`, and `synthesis_error_summary`.

Example `POST /runs` payload fields:

```json
{
  "task": "Read ./README.md and summarize it",
  "provider": "builtin",
  "model": "deterministic",
  "session_id": 1,
  "enabled_skills": ["filesystem", "fetch"],
  "execute_now": true
}
```

## Provider configuration (OpenAI + Ollama)

OpenAI adapter env vars:

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"   # optional
export OPENAI_TIMEOUT_SECONDS="30"                    # optional
```

Registry also considers `AGENTHUB_OPENAI_API_KEY` for configured-state checks.

Ollama adapter env vars:

```bash
export OLLAMA_BASE_URL="http://localhost:11434"       # optional
export OLLAMA_TIMEOUT_SECONDS="30"                    # optional
```

Default model hints currently exposed by capability metadata:
- OpenAI: `gpt-4o-mini`, `gpt-4.1-mini`
- Ollama: `llama3.1`, `qwen2.5`

## Provider endpoints

```bash
# list providers and configuration status
curl -s http://localhost:8000/providers | jq

# list provider model metadata (all providers)
curl -s http://localhost:8000/providers/models | jq

# list provider model metadata for one provider
curl -s "http://localhost:8000/providers/models?provider=ollama" | jq

# check a provider
curl -s -X POST http://localhost:8000/providers/health-check \
  -H 'Content-Type: application/json' \
  -d '{"provider":"ollama"}' | jq
```

## Dashboard run detail page

- Run detail route: `/runs/[id]` (example: `http://localhost:3000/runs/12`).
- Purpose: show run summary + final output + ordered trace timeline for debugging plan/executor/synthesis behavior.
- The trace timeline renders events from `GET /runs/{run_id}/trace` including tool and synthesis lifecycle entries.

## Current limitations / explicit non-goals

- No model-driven planner/autonomous reasoning in planning stage (planner remains deterministic).
- No async/background run workers (`execute_now=false` is not the primary flow for this milestone).
- No browser/shell/voice/OCR/multi-agent orchestration.
- Provider endpoints currently report registry/configuration metadata and lightweight health responses, not full credential diagnostics.
