# AgentHub Roadmap (v0.1)

## Goal
Ship a minimal local-first platform foundation with one bounded runtime, one skill system, one model gateway, one dashboard, and one trace system.

## Milestones
1. Root-level monorepo scaffold and accurate developer docs.
2. FastAPI backend with persistence-backed health/sessions/runs/catalog endpoints.
3. Read-only filesystem skill slice with workspace safety controls.
4. Next.js dashboard shell wired to `POST /runs` with clear run feedback.
5. Completed: synchronous alpha execution loop with deterministic planning, executable filesystem/fetch skills, trace-rich run completion, and dashboard run result panel.
6. Completed: deterministic research workflow with `web_search`, bounded search->fetch execution, evidence aggregation, and improved synthesis/trace visibility.
7. Completed: local installable skill catalog with runtime-typed manifests, SQLite-backed skill persistence, MCP stdio wrapping, enable/disable/test flows, and a skills management UI.
8. Completed: persisted per-skill configuration, env-var-name secret bindings, readiness checks, config-aware MCP env injection, and redacted skill config/test UX.
9. Completed: optional model-assisted planning with enabled/ready skill discovery, capability metadata, bounded budgets, planning validation, deterministic fallback, and planning-aware run/UI traces.
10. Completed: async local run orchestration with queued/running/waiting/cancelled lifecycle, approval pause/resume checkpoints, cooperative cancellation, SSE progress streaming, and preserved deterministic/model-assisted planning paths.
11. Next: improve restart resilience and timestamp hygiene by making step replay semantics more explicitly idempotent and replacing remaining `datetime.utcnow()` usage with timezone-aware UTC timestamps.
