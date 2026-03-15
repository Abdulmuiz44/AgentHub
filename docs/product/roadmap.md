# AgentHub Roadmap (v0.1)

## Goal
Ship a minimal local-first platform foundation with one deterministic runtime, one skill system, one model gateway, one dashboard, and one trace system.

## Milestones
1. Root-level monorepo scaffold and accurate developer docs.
2. FastAPI backend with persistence-backed health/sessions/runs/catalog endpoints.
3. Read-only filesystem skill slice with workspace safety controls.
4. Next.js dashboard shell wired to `POST /runs` with clear run feedback.
5. ✅ Synchronous alpha execution loop with deterministic planning, executable filesystem/fetch skills, trace-rich run completion, and dashboard run result panel.
6. ✅ Deterministic research workflow with `web_search`, bounded search->fetch execution, evidence aggregation, and improved synthesis/trace visibility.
7. Next: incremental quality improvements for summarization and provider prompts while keeping deterministic planning explicit and inspectable.
