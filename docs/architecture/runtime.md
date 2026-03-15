# Runtime Architecture (Deterministic Local Skill Platform Slice)

## Components
- **API (`apps/api`)**: creates runs, exposes run/trace routes, and exposes typed skill catalog/install/enable/disable/test routes.
- **Core (`packages/core`)**: deterministic planner, bounded executor, evidence aggregation, synthesis engine, and runtime contracts.
- **Skill catalog service (`apps/api/app/services/skills.py`)**: seeds built-ins, persists local skill definitions, loads manifests, tests skills, and builds runtime registries.
- **Memory (`packages/memory`)**: SQLModel entities and SQLite repositories for sessions, runs, traces, approvals, providers, and skill definitions.
- **Skills (`packages/skills`)**: shared manifest spec, native built-in skills, MCP stdio wrapper, and unified skill registry.
- **Web (`apps/web`)**: dashboard, run detail UI, and a practical skills management page.

## Skill platform flow
1. Built-in native skills are defined in code with typed manifests.
2. On demand, the skill catalog service seeds built-ins into SQLite-backed `SkillDefinition` records.
3. Local manifests can be installed through `POST /skills/install` or loaded from a manifest path.
4. Skill definitions persist runtime type, enabled state, manifest/config, tags/scopes, install source, and last test result.
5. The catalog service builds a runtime `SkillRegistry` from enabled skill definitions.
6. Planner behavior stays deterministic:
   - normal built-in heuristics for file/url/research tasks
   - explicit routing for `Use skill <name> ...`
7. Executor invokes both native and MCP stdio skills through the same request/result contract.
8. Trace events include compact runtime metadata such as skill name, runtime type, built-in vs installed, and result summaries.

## Runtime types
Supported in this milestone:
- `native_python`
- `mcp_stdio`

Reserved for future expansion:
- `mcp_http`
- `subprocess_tool`

## Manifest shape
The shared manifest spec includes:
- `name`, `version`, `description`
- `runtime_type`
- `scopes`, `permissions`, `tags`
- `enabled_by_default`
- `input_schema_summary`, `output_schema_summary`
- `capabilities`
- `install_source`
- `test_input`
- `mcp_stdio` config for stdio-backed skills:
  - `command`
  - `args`
  - `env_var_refs`
  - `working_directory`
  - `startup_timeout_seconds`
  - `call_timeout_seconds`
  - `tool_name`

## MCP stdio wrapper behavior
The local MCP stdio wrapper intentionally stays small:
- launches a configured stdio process
- sends `initialize`
- discovers tools via `tools/list`
- invokes a selected tool via `tools/call`
- normalizes the response into the shared AgentHub `SkillResult`
- shuts down cleanly with `shutdown` and `exit`

Current limits:
- stdio only
- tool invocation only
- no MCP resources/prompts workflow
- one process per execution/test call

## Current limitations
- The current repository runtime still executes runs synchronously in-request.
- Skill installation is local-manifest only.
- Native built-ins are still the only heuristically selected skills unless the task explicitly names an installed skill.
- Trace payloads remain compact and do not store full raw MCP protocol exchanges.
