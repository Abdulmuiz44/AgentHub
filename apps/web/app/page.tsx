"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  CreateRunResult,
  ProviderCapability,
  checkProviderHealth,
  createRun,
  listProviderModels,
  listProviders,
} from "../lib/api";

export default function DashboardPage() {
  const [task, setTask] = useState("");
  const [providers, setProviders] = useState<ProviderCapability[]>([]);
  const [provider, setProvider] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [providerHealth, setProviderHealth] = useState<string | null>(null);
  const [isLoadingProviders, setIsLoadingProviders] = useState(true);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<CreateRunResult | null>(null);
  const enabledSkills = useMemo(() => ["filesystem", "fetch"], []);

  useEffect(() => {
    let active = true;

    async function loadProviders() {
      setIsLoadingProviders(true);
      try {
        const data = await listProviders();
        if (!active) {
          return;
        }

        setProviders(data);
        if (data.length === 0) {
          setMessage("No providers were returned by the backend.");
          return;
        }

        const defaultProvider = data[0].name;
        const defaultModels = data[0].models;
        setProvider(defaultProvider);
        setModels(defaultModels);
        setModel(defaultModels[0] ?? "");
      } catch (error) {
        if (!active) {
          return;
        }
        setMessage(error instanceof Error ? error.message : "Failed to load providers");
      } finally {
        if (active) {
          setIsLoadingProviders(false);
        }
      }
    }

    void loadProviders();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!provider) {
      return;
    }

    let active = true;
    async function loadModelsAndHealth() {
      setIsLoadingModels(true);
      try {
        const [providerModels, health] = await Promise.all([listProviderModels(provider), checkProviderHealth(provider)]);
        if (!active) {
          return;
        }

        setModels(providerModels);
        setModel((prev) => (providerModels.includes(prev) ? prev : providerModels[0] ?? ""));
        setProviderHealth(health.message ?? (health.healthy ? "Healthy" : "Unhealthy"));
      } catch (error) {
        if (!active) {
          return;
        }

        setModels([]);
        setModel("");
        setProviderHealth(null);
        setMessage(error instanceof Error ? error.message : "Failed to load provider models");
      } finally {
        if (active) {
          setIsLoadingModels(false);
        }
      }
    }

    void loadModelsAndHealth();
    return () => {
      active = false;
    };
  }, [provider]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage(null);
    setRunResult(null);
    setIsSubmitting(true);
    try {
      const result = await createRun({ task, provider, model, enabled_skills: enabledSkills, execute_now: true });
      setRunResult(result);
      const synthesisMode = result.run.synthesis_mode ?? "n/a";
      const synthesisStatus = result.run.synthesis_status ?? "n/a";
      setMessage(
        `Run #${result.run.id} finished with status ${result.run.status} (synthesis mode: ${synthesisMode}, synthesis status: ${synthesisStatus}).`
      );
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
            onChange={(e) => setProvider(e.target.value)}
            disabled={isLoadingProviders || providers.length === 0}
          >
            {providers.map((item) => (
              <option key={item.name} value={item.name}>
                {item.display_name}
              </option>
            ))}
          </select>
          {providerHealth ? <p className="mt-1 text-xs text-slate-400">Provider health: {providerHealth}</p> : null}
        </div>

        <div>
          <label className="mb-1 block text-sm">Model selector</label>
          <select
            className="w-full rounded bg-slate-900 p-2"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            disabled={isLoadingModels || models.length === 0}
          >
            {models.map((item) => (
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
          disabled={isSubmitting || !provider || !model || isLoadingProviders || isLoadingModels}
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
          <p className="text-sm">Synthesis mode: {runResult.run.synthesis_mode ?? "n/a"}</p>
          <p className="text-sm">Synthesis status: {runResult.run.synthesis_status ?? "n/a"}</p>
          <p className="text-sm whitespace-pre-wrap">Final output: {runResult.run.final_output ?? "(none)"}</p>
          <p className="text-sm">
            <Link href={`/runs/${runResult.run.id}`} className="text-blue-400 underline hover:text-blue-300">
              Open full run details
            </Link>
          </p>
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
