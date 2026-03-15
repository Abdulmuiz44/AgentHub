"use client";

import { FormEvent, useMemo, useState } from "react";

import { CreateRunResult, createRun } from "../lib/api";

const providers = ["ollama", "openai", "builtin"];
const modelsByProvider: Record<string, string[]> = {
  ollama: ["llama3.1", "qwen2.5"],
  openai: ["gpt-4o-mini", "gpt-4.1-mini"],
  builtin: ["deterministic"],
};

export default function DashboardPage() {
  const [task, setTask] = useState("");
  const [provider, setProvider] = useState("builtin");
  const [model, setModel] = useState(modelsByProvider.builtin[0]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<CreateRunResult | null>(null);
  const enabledSkills = useMemo(() => ["filesystem", "fetch"], []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setRunResult(null);
    setIsSubmitting(true);
    try {
      const result = await createRun({ task, provider, model, enabled_skills: enabledSkills, execute_now: true });
      setRunResult(result);
      setMessage(`Run #${result.run.id} finished with status ${result.run.status}.`);
      setTask("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unexpected error");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-3xl font-semibold">AgentHub Dashboard</h1>
      <form onSubmit={onSubmit} className="space-y-4 rounded-lg border border-slate-800 p-4">
        <div>
          <label className="mb-1 block text-sm">Task input</label>
          <textarea
            className="w-full rounded bg-slate-900 p-2"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            placeholder="Describe the task"
            required
          />
        </div>

        <div>
          <label className="mb-1 block text-sm">Provider selector</label>
          <select
            className="w-full rounded bg-slate-900 p-2"
            value={provider}
            onChange={(e) => {
              const nextProvider = e.target.value;
              setProvider(nextProvider);
              setModel(modelsByProvider[nextProvider][0]);
            }}
          >
            {providers.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm">Model selector</label>
          <select className="w-full rounded bg-slate-900 p-2" value={model} onChange={(e) => setModel(e.target.value)}>
            {modelsByProvider[provider].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>

        <div>
          <p className="text-sm text-slate-300">Enabled skills summary: {enabledSkills.join(", ")} (read-only)</p>
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded bg-blue-600 px-4 py-2 hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isSubmitting ? "Executing run..." : "Submit"}
        </button>
      </form>
      {message ? <p className="mt-4 text-sm text-slate-200">{message}</p> : null}

      {runResult ? (
        <section className="mt-6 space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Run Result</h2>
          <p className="text-sm">Run ID: {runResult.run.id}</p>
          <p className="text-sm">Status: {runResult.run.status}</p>
          <p className="text-sm whitespace-pre-wrap">Final output: {runResult.run.final_output ?? "(none)"}</p>
          <div>
            <p className="text-sm font-medium">Trace preview</p>
            <ul className="list-disc pl-5 text-xs text-slate-300">
              {runResult.trace_events.slice(0, 5).map((event) => (
                <li key={event.id}>{event.event_type}</li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}
    </main>
  );
}
