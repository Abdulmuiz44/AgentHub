# AgentHub Roadmap (v0.1)

## Goal
Ship a minimal local-first platform foundation with one runtime, one skill system, one model gateway, one dashboard, and one trace system.

## Milestones
1. Root-level monorepo scaffold and accurate developer docs.
2. FastAPI backend with persistence-backed health/sessions/runs/catalog endpoints.
3. Read-only filesystem skill slice with workspace safety controls.
4. Next.js dashboard shell wired to `POST /runs` with clear run feedback.
5. ✅ Synchronous alpha runtime with deterministic planner+executor as source of truth, executable filesystem/fetch skills, persisted trace timeline, synthesis stage (provider path + deterministic fallback), provider inspection endpoints (`/providers`, `/providers/models`, `/providers/health-check`), and run detail route (`/runs/[id]`).
6. Next: model-guided planning/execution without breaking deterministic fallback behavior, trace contracts, or persistence guarantees.

## Milestone 5 scope guardrails (current)

### In-scope
- Deterministic tool planning and execution.
- Synthesis metadata persisted on runs (`synthesis_mode`, `synthesis_status`, `synthesis_error_summary`).
- Provider registry/configuration visibility and lightweight health checks.
- Dashboard run detail + trace timeline for runtime observability.

### Explicit non-goals
- Replacing deterministic planner with autonomous planning.
- Async/background run orchestration.
- Browser/shell/voice/OCR or multi-agent surfaces.
- Full provider management UX (secrets lifecycle, quota management, advanced diagnostics).
