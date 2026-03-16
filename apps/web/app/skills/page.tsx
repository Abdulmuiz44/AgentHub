"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import {
  SkillConfigResponse,
  SkillResponse,
  getSkillConfig,
  installSkill,
  listSkills,
  setSkillEnabled,
  testSkill,
  updateSkillConfig,
} from "../../lib/api";

type ConfigDraft = {
  values: Record<string, string>;
  secret_bindings: Record<string, string>;
};

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [details, setDetails] = useState<Record<string, SkillConfigResponse>>({});
  const [drafts, setDrafts] = useState<Record<string, ConfigDraft>>({});
  const [manifestPath, setManifestPath] = useState("");
  const [manifestJson, setManifestJson] = useState(`{
  "name": "echo-mcp",
  "version": "0.1.0",
  "description": "Example local MCP skill",
  "runtime_type": "mcp_stdio",
  "enabled_by_default": true,
  "scopes": ["local:test"],
  "tags": ["mcp", "local"],
  "config_fields": [
    {
      "key": "API_KEY",
      "label": "API key",
      "required": true,
      "secret": true,
      "value_type": "string",
      "env_var_allowed": true,
      "description": "Bind to an environment variable name"
    }
  ],
  "capabilities": [{ "operation": "execute", "read_only": true }],
  "mcp_stdio": {
    "command": "python",
    "args": ["scripts/mcp_echo_server.py"],
    "tool_name": "echo",
    "env_map": { "ECHO_API_KEY": "API_KEY" }
  }
}`);
  const [message, setMessage] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function refresh() {
    const nextSkills = await listSkills();
    setSkills(nextSkills);
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function loadSkillDetail(skillName: string) {
    const detail = await getSkillConfig(skillName);
    setDetails((current) => ({ ...current, [skillName]: detail }));
    setDrafts((current) => {
      if (current[skillName]) {
        return current;
      }
      const values: Record<string, string> = {};
      const secretBindings: Record<string, string> = {};
      for (const item of detail.state.values) {
        if (item.uses_environment_binding) {
          secretBindings[item.key] = String(item.secret_binding ?? "");
        } else {
          values[item.key] = item.value === undefined || item.value === null ? "" : String(item.value);
        }
      }
      return { ...current, [skillName]: { values, secret_bindings: secretBindings } };
    });
  }

  async function onInstall(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsBusy(true);
    setMessage(null);
    try {
      const payload = manifestPath.trim()
        ? { manifest_path: manifestPath.trim() }
        : { manifest: JSON.parse(manifestJson) as Record<string, unknown> };
      const installed = await installSkill(payload);
      setMessage(`Installed ${installed.name} (${installed.runtime_type}).`);
      await refresh();
      await loadSkillDetail(installed.name);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Install failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function onToggle(skill: SkillResponse) {
    setIsBusy(true);
    setMessage(null);
    try {
      await setSkillEnabled(skill.name, !skill.enabled);
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Toggle failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function onTest(skill: SkillResponse) {
    setIsBusy(true);
    setMessage(null);
    try {
      const result = await testSkill(skill.name);
      setMessage(`${result.skill.name}: ${result.summary}`);
      await refresh();
      await loadSkillDetail(skill.name);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Test failed");
    } finally {
      setIsBusy(false);
    }
  }

  async function onSaveConfig(skill: SkillResponse) {
    const draft = drafts[skill.name];
    if (!draft) {
      return;
    }
    setIsBusy(true);
    setMessage(null);
    try {
      const values = Object.fromEntries(
        Object.entries(draft.values).filter(([, value]) => value.trim() !== "")
      );
      const secret_bindings = Object.fromEntries(
        Object.entries(draft.secret_bindings).filter(([, value]) => value.trim() !== "")
      );
      const updated = await updateSkillConfig(skill.name, { values, secret_bindings });
      setMessage(`Saved config for ${updated.name}.`);
      await refresh();
      await loadSkillDetail(skill.name);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Save failed");
    } finally {
      setIsBusy(false);
    }
  }

  function updateDraft(skillName: string, key: string, value: string, secret: boolean) {
    setDrafts((current) => {
      const existing = current[skillName] ?? { values: {}, secret_bindings: {} };
      return {
        ...current,
        [skillName]: secret
          ? { ...existing, secret_bindings: { ...existing.secret_bindings, [key]: value } }
          : { ...existing, values: { ...existing.values, [key]: value } },
      };
    });
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Skills</h1>
        <Link href="/" className="text-sm text-blue-400 underline hover:text-blue-300">Back to dashboard</Link>
      </div>

      <section className="rounded-lg border border-slate-800 p-4">
        <h2 className="text-lg font-medium">Install local skill</h2>
        <form onSubmit={onInstall} className="mt-3 space-y-3">
          <input className="w-full rounded bg-slate-900 p-2 text-sm" value={manifestPath} onChange={(e) => setManifestPath(e.target.value)} placeholder="Optional manifest path (JSON file)" />
          <textarea className="min-h-80 w-full rounded bg-slate-900 p-2 font-mono text-xs" value={manifestJson} onChange={(e) => setManifestJson(e.target.value)} />
          <button type="submit" disabled={isBusy} className="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500 disabled:opacity-60">Install skill</button>
        </form>
      </section>

      {message ? <p className="text-sm text-slate-200">{message}</p> : null}

      <section className="space-y-3">
        {skills.map((skill) => {
          const detail = details[skill.name];
          const draft = drafts[skill.name] ?? { values: {}, secret_bindings: {} };
          return (
            <article key={skill.name} className="rounded-lg border border-slate-800 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-medium">{skill.name}</h2>
                  <p className="text-sm text-slate-300">{skill.description}</p>
                  <p className="text-xs text-slate-400">Runtime: {skill.runtime_type} | {skill.is_builtin ? "built-in" : "installed"} | Scopes: {skill.scopes.join(", ") || "none"}</p>
                  <p className="text-xs text-slate-400">Readiness: {skill.readiness_status} - {skill.readiness_summary}</p>
                  <p className="text-xs text-slate-400">Last test: {skill.last_test_status ?? "never"}{skill.last_test_summary ? ` - ${skill.last_test_summary}` : ""}</p>
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={() => void loadSkillDetail(skill.name)} disabled={isBusy} className="rounded border border-slate-600 px-3 py-2 text-sm">
                    {detail ? "Refresh config" : "Configure"}
                  </button>
                  <button type="button" onClick={() => void onToggle(skill)} disabled={isBusy} className="rounded border border-slate-600 px-3 py-2 text-sm">
                    {skill.enabled ? "Disable" : "Enable"}
                  </button>
                  <button type="button" onClick={() => void onTest(skill)} disabled={isBusy} className="rounded bg-emerald-700 px-3 py-2 text-sm text-emerald-100 disabled:opacity-60">
                    Test
                  </button>
                </div>
              </div>

              {detail ? (
                <div className="mt-4 space-y-3 rounded border border-slate-800 bg-slate-950/60 p-4">
                  <div>
                    <h3 className="text-sm font-medium">Configuration</h3>
                    <p className="text-xs text-slate-400">Secret fields store environment variable names only. Resolved secret values are never shown.</p>
                  </div>
                  {detail.config_schema.length === 0 ? <p className="text-sm text-slate-300">This skill does not require additional configuration.</p> : null}
                  {detail.config_schema.map((field) => {
                    const currentValue = field.secret ? draft.secret_bindings[field.key] ?? "" : draft.values[field.key] ?? "";
                    return (
                      <label key={field.key} className="block space-y-1 text-sm">
                        <span className="font-medium">{field.label ?? field.key} {field.required ? "*" : ""}</span>
                        {field.description ? <span className="block text-xs text-slate-400">{field.description}</span> : null}
                        <input
                          value={currentValue}
                          onChange={(event) => updateDraft(skill.name, field.key, event.target.value, field.secret)}
                          placeholder={field.secret ? "ENV_VAR_NAME" : String(field.example ?? field.default ?? "")}
                          className="w-full rounded bg-slate-900 p-2 text-sm"
                        />
                        <span className="block text-xs text-slate-500">
                          {field.secret ? "Stored as env var binding" : `Type: ${field.value_type}`}
                        </span>
                      </label>
                    );
                  })}
                  <button type="button" onClick={() => void onSaveConfig(skill)} disabled={isBusy} className="rounded bg-sky-700 px-3 py-2 text-sm text-sky-100 disabled:opacity-60">
                    Save config
                  </button>
                </div>
              ) : null}

              <pre className="mt-3 whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(skill.manifest, null, 2)}</pre>
            </article>
          );
        })}
      </section>
    </main>
  );
}
