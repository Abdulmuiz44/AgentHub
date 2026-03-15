# Runtime Architecture (Current Foundation)

## Components
- **API (`apps/api`)**: HTTP routes for health, sessions, runs, traces, providers, and skills.
- **Core (`packages/core`)**: Typed runtime contracts and minimal planner/executor/task-runner structure.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite access helpers.
- **Models (`packages/models`)**: Provider abstraction and registry (Ollama + OpenAI metadata).
- **Skills (`packages/skills`)**: Skill manifest/types and read-only filesystem skill.
- **Web (`apps/web`)**: Dashboard that submits run requests.

## Flow implemented now
1. Dashboard submits `POST /runs`.
2. API creates/attaches session.
3. API persists run.
4. API writes initial trace events (`run.started`, `plan.created`).
5. API returns run metadata + trace event records.

## Non-goals for this milestone
- Full LLM-driven execution loop
- Browser/shell automation skills
- Multi-agent orchestration
