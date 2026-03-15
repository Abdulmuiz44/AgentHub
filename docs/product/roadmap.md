# AgentHub Roadmap (v0.1)

## Goal
Ship a minimal local-first platform foundation with one runtime, one skill system, one model gateway, one dashboard, and one trace system.

## Milestones
1. Root-level monorepo scaffold and accurate developer docs.
2. FastAPI backend with persistence-backed health/sessions/runs/catalog endpoints.
3. Read-only filesystem skill slice with workspace safety controls.
4. Next.js dashboard shell wired to `POST /runs` with clear run feedback.
5. ✅ Synchronous alpha execution loop with deterministic planning, executable filesystem/fetch skills, trace-rich run completion, optional provider synthesis fallback, and dashboard run result panel.
6. ✅ Provider catalog expansion (`/providers`, `/providers/models`, `/providers/health-check`) and synthesis metadata returned in run creation responses.
7. Next: model-guided planning/execution while preserving deterministic fallback and trace contract stability.

## Run detail page usage (current)
- Submit tasks from the dashboard and inspect `run.status`, `run.final_output`, and persisted trace events.
- Use `trace_events` + `execution_metadata` from `POST /runs` to display synthesis state (`completed`, `skipped`, `failed`) without requiring live provider calls.
- For provider-backed synthesis demos, set OpenAI/Ollama env vars locally; if omitted, runtime safely degrades to deterministic output.
