# AgentHub v0.1 Alpha Runtime Slice

AgentHub is a local-first, cloud-optional platform for running AI agents.

This repository currently includes:
- FastAPI backend with SQLite-backed sessions, runs, traces, approvals, provider metadata, and a persisted skill catalog
- Deterministic bounded execution with built-in native skills for filesystem, fetch, and web search
- Local installable skill management for native and MCP stdio-backed skills
- Per-skill persisted configuration with readiness checks and environment-variable secret bindings
- Lightweight MCP stdio wrapping for initialize, tools discovery, tool calls, config-aware env injection, and clean shutdown
- Next.js dashboard, run detail page, and a simple skills management view

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

## Skill platform

AgentHub now has a real local skill catalog with two runtime types:
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

Skill manifests include typed metadata such as:
- `name`, `version`, `description`
- `runtime_type`
- `scopes`, `tags`, `permissions`
- `input_schema_summary`, `output_schema_summary`
- `capabilities`
- `config_fields`
- `mcp_stdio` command/config for stdio-backed skills

Built-in skills are seeded into the same SQLite-backed catalog as installed local skills so the UI and API can inspect them consistently.

## Skill configuration and secret handling

Skills can declare configuration requirements through `config_fields`.
Each field can define:
- `key`, `label`, `description`
- `required`
- `secret`
- `value_type`
- `default`
- `env_var_allowed`

Persistence rules in this milestone:
- non-secret config values are stored in SQLite
- secret values are not stored
- secret fields store environment variable names only
- runtime resolves those env var names from `os.environ`
- readiness is exposed as `ready`, `missing_required_config`, `missing_required_env_binding`, or `invalid_config`

Redaction rules in this milestone:
- raw secret values are not accepted for persistence
- raw secret values are not returned from skill APIs
- traces and test results redact resolved secret values
- UI shows whether a secret binding is configured and which env var name is bound

## MCP stdio support

This milestone adds bounded MCP stdio support for local tool wrapping only:
- start a configured stdio server process
- send `initialize`
- call `tools/list`
- call `tools/call`
- map configured skill fields into process env safely
- normalize tool results into the shared AgentHub skill contract
- shut down cleanly

Current MCP scope limits:
- stdio only
- tool execution only
- no MCP resources/prompts UI yet
- no remote registry or hosted skill distribution
- no encrypted secret storage; secret binding is env-name based only

## Explicit installed-skill routing

The planner remains deterministic. It does not do model-driven tool selection.

Installed skills can be exercised explicitly by naming them in the task, for example:
- `Use skill echo_mcp_test to summarize this input`

When that pattern is used, the plan records an explicit selection reason and traces include the selected skill, runtime type, readiness state, and whether it was built-in or installed.

## Search configuration

- `AGENTHUB_SEARCH_PROVIDER` (optional): `searxng`, `duckduckgo`, or `duckduckgo_instant`
- `AGENTHUB_SEARXNG_BASE_URL` (optional): required when provider is `searxng`

## Current limits

- Local skill install only; no remote marketplace or publishing flow
- Built-in deterministic runtime remains synchronous in the current repository state
- MCP support is intentionally narrow and focused on stdio tool calls
- No model-driven routing, distributed workers, browser marketplace UX, or hosted sync
- Temp validation folders such as `.deps/` and `apps/api/.vendor/` are ignored and should not be committed
