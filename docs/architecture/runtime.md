# Runtime Architecture (Synchronous Alpha)

## Components
- **API (`apps/api`)**: creates runs, executes runtime synchronously, persists run + traces, exposes run/trace/provider routes.
- **Core (`packages/core`)**: deterministic planner, synchronous executor, synthesis engine, task runner, structured runtime contracts.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions/runs/traces.
- **Skills (`packages/skills`)**: executable skill interfaces and built-in `filesystem` + `fetch` skills.
- **Models (`packages/models`)**: provider adapters + registry for OpenAI and Ollama.
- **Web (`apps/web`)**: dashboard submission flow plus run detail page (`/runs/[id]`) with trace timeline.

## Source of truth: deterministic planner + executor

The planner/executor path is authoritative for what work is performed:
1. `Planner.create_plan()` applies URL/filepath heuristics only.
2. `Executor.execute()` runs planned tool steps and emits trace events.
3. Only after deterministic execution completes does synthesis format/refine final output.

This means providers do **not** decide what tools run in this milestone.

## Runtime flow
1. Client calls `POST /runs` with fields like `task`, `provider`, `model`, `enabled_skills`, `execute_now`.
2. API creates/attaches a session and persists run status (`pending` -> `running`).
3. `TaskRunner` records `run.started`, creates deterministic plan (`plan.created`), and executes steps.
4. Executor emits tool lifecycle events in order:
   - `tool.requested`
   - `tool.started`
   - `tool.completed` or `tool.failed`
5. `TaskRunner` starts synthesis (`synthesis.started`) and chooses:
   - **Provider synthesis**: when a configured provider adapter is available.
   - **Deterministic fallback synthesis**: when provider/model are builtin/deterministic, missing, unavailable, or provider call errors.
6. Runtime emits:
   - `synthesis.failed` when provider path fails and fallback is used with an error summary.
   - `synthesis.completed` with metadata (`mode`, `status`, `provider`, `model`, optional `error_summary`).
7. Runtime emits terminal event (`run.completed` or `run.failed`).
8. API persists ordered trace events and run fields:
   - `status`
   - `final_output`
   - `synthesis_mode`
   - `synthesis_status`
   - `synthesis_error_summary`

## API schema fields (implemented)

`RunCreateRequest`:
- `task: str`
- `provider: str = "builtin"`
- `model: str = "deterministic"`
- `session_id: int | None`
- `enabled_skills: list[str]`
- `execute_now: bool = true`

`RunResponse` includes synthesis fields:
- `synthesis_mode: str | null`
- `synthesis_status: str | null`
- `synthesis_error_summary: str | null`

## Provider integration and endpoints

### Environment configuration

OpenAI:
```bash
export OPENAI_API_KEY="..."
export AGENTHUB_OPENAI_API_KEY="..."                 # used by provider configured-state check
export OPENAI_BASE_URL="https://api.openai.com/v1"   # optional override
export OPENAI_TIMEOUT_SECONDS="30"                    # optional override
```

Ollama:
```bash
export OLLAMA_BASE_URL="http://localhost:11434"       # optional override
export OLLAMA_TIMEOUT_SECONDS="30"                    # optional override
```

Capability model hints currently surfaced via `/providers` and `/providers/models`:
- OpenAI: `gpt-4o-mini`, `gpt-4.1-mini`
- Ollama: `llama3.1`, `qwen2.5`

### Endpoint usage

```bash
curl -s http://localhost:8000/providers | jq
curl -s http://localhost:8000/providers/models | jq
curl -s "http://localhost:8000/providers/models?provider=openai" | jq
curl -s -X POST http://localhost:8000/providers/health-check \
  -H 'Content-Type: application/json' \
  -d '{"provider":"openai"}' | jq
```

Response fields to expect:
- `/providers`: `provider`, `configuration_status`, `is_configured`
- `/providers/models`: `providers[]` with `provider_name`, `display_name`, `configuration_status`, `is_configured`, `models`
- `/providers/health-check`: `provider`, `configuration_status`, `healthy`, `message`

## Web run detail route and trace timeline

- Route: `apps/web/app/runs/[id]/page.tsx` -> `/runs/[id]`.
- Pulls data from:
  - `GET /runs/{id}` for summary fields (including synthesis metadata)
  - `GET /runs/{id}/trace` for ordered timeline
- Timeline purpose: operational debugging for plan creation, tool execution sequence, and synthesis fallback/provider outcomes.

## Known limitations and non-goals (this milestone)

- Deterministic planner remains fixed to URL/filepath heuristics only.
- No asynchronous queue/worker runtime for long-running jobs.
- No autonomous browser/shell execution, no OCR/voice, no multi-agent choreography.
- Synthesis provider path is best-effort; deterministic fallback is expected and valid behavior.
