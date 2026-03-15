"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";

import { SkillResponse, installSkill, listSkills, setSkillEnabled, testSkill } from "../../lib/api";

export default function SkillsPage() {
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [manifestPath, setManifestPath] = useState("");
  const [manifestJson, setManifestJson] = useState(`{
  "name": "echo-mcp",
  "version": "0.1.0",
  "description": "Example local MCP skill",
  "runtime_type": "mcp_stdio",
  "enabled_by_default": true,
  "scopes": ["local:test"],
  "tags": ["mcp", "local"],
  "capabilities": [{ "operation": "execute", "read_only": true }],
  "mcp_stdio": {
    "command": "python",
    "args": ["scripts/mcp_echo_server.py"],
    "tool_name": "echo"
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
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Test failed");
    } finally {
      setIsBusy(false);
    }
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
          <textarea className="min-h-64 w-full rounded bg-slate-900 p-2 font-mono text-xs" value={manifestJson} onChange={(e) => setManifestJson(e.target.value)} />
          <button type="submit" disabled={isBusy} className="rounded bg-blue-600 px-4 py-2 text-sm hover:bg-blue-500 disabled:opacity-60">Install skill</button>
        </form>
      </section>

      {message ? <p className="text-sm text-slate-200">{message}</p> : null}

      <section className="space-y-3">
        {skills.map((skill) => (
          <article key={skill.name} className="rounded-lg border border-slate-800 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-medium">{skill.name}</h2>
                <p className="text-sm text-slate-300">{skill.description}</p>
                <p className="text-xs text-slate-400">Runtime: {skill.runtime_type} | {skill.is_builtin ? "built-in" : "installed"} | Scopes: {skill.scopes.join(", ") || "none"}</p>
                <p className="text-xs text-slate-400">Last test: {skill.last_test_status ?? "never"}{skill.last_test_summary ? ` - ${skill.last_test_summary}` : ""}</p>
              </div>
              <div className="flex gap-2">
                <button type="button" onClick={() => onToggle(skill)} disabled={isBusy} className="rounded border border-slate-600 px-3 py-2 text-sm">
                  {skill.enabled ? "Disable" : "Enable"}
                </button>
                <button type="button" onClick={() => onTest(skill)} disabled={isBusy} className="rounded bg-emerald-700 px-3 py-2 text-sm text-emerald-100 disabled:opacity-60">
                  Test
                </button>
              </div>
            </div>
            <pre className="mt-3 whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs text-slate-300">{JSON.stringify(skill.manifest, null, 2)}</pre>
          </article>
        ))}
      </section>
    </main>
  );
}
