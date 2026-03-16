"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { RunResponse, StreamEnvelope, TraceResponse, approveRunStep, buildRunStreamUrl, cancelRun, denyRunStep, fetchRunDetail, fetchRunTrace } from "../../../lib/api";

type ParsedTraceEvent = TraceResponse & { parsedPayload: Record<string, unknown> | null };

function parsePayload(payload: string): Record<string, unknown> | null {
  try {
    return JSON.parse(payload) as Record<string, unknown>;
  } catch (_error) {
    return null;
  }
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = Number(params.id);
  const [run, setRun] = useState<RunResponse | null>(null);
  const [trace, setTrace] = useState<ParsedTraceEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(runId)) {
      setError("Invalid run id.");
      setIsLoading(false);
      return;
    }

    let active = true;
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const [runDetail, traceItems] = await Promise.all([fetchRunDetail(runId), fetchRunTrace(runId)]);
        if (!active) return;
        setRun(runDetail);
        setTrace(traceItems.map((item) => ({ ...item, parsedPayload: parsePayload(item.payload) })));
      } catch (loadError) {
        if (!active) return;
        setError(loadError instanceof Error ? loadError.message : "Failed to load run detail.");
      } finally {
        if (active) setIsLoading(false);
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [runId]);

  useEffect(() => {
    if (!run || ["completed", "failed", "cancelled"].includes(run.status)) {
      return;
    }
    const source = new EventSource(buildRunStreamUrl(runId));
    source.onmessage = (event) => {
      const envelope = JSON.parse(event.data) as StreamEnvelope;
      if (envelope.type === "run") {
        setRun(envelope.data);
        return;
      }
      setTrace((current) => {
        if (current.some((item) => item.id === envelope.data.id)) {
          return current;
        }
        return [...current, { ...envelope.data, parsedPayload: parsePayload(envelope.data.payload) }];
      });
    };
    source.onerror = () => {
      source.close();
    };
    return () => {
      source.close();
    };
  }, [run, runId]);

  async function onCancel() {
    if (!run) return;
    setIsMutating(true);
    setError(null);
    try {
      const updated = await cancelRun(run.id);
      setRun(updated);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "Failed to cancel run.");
    } finally {
      setIsMutating(false);
    }
  }

  async function onApprove() {
    if (!run?.pending_approval) return;
    setIsMutating(true);
    setError(null);
    try {
      const updated = await approveRunStep(run.id, run.pending_approval.id);
      setRun(updated.run);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "Failed to approve run.");
    } finally {
      setIsMutating(false);
    }
  }

  async function onDeny() {
    if (!run?.pending_approval) return;
    setIsMutating(true);
    setError(null);
    try {
      const updated = await denyRunStep(run.id, run.pending_approval.id);
      setRun(updated.run);
    } catch (mutationError) {
      setError(mutationError instanceof Error ? mutationError.message : "Failed to deny run.");
    } finally {
      setIsMutating(false);
    }
  }

  const toolEvents = useMemo(() => trace.filter((event) => event.event_type.startsWith("tool.")), [trace]);
  const synthesisEvents = useMemo(() => trace.filter((event) => event.event_type.startsWith("synth")), [trace]);
  const planningEvents = useMemo(() => trace.filter((event) => event.event_type.startsWith("planning") || event.event_type.startsWith("plan.") || event.event_type.startsWith("budget.")), [trace]);
  const skillSummaries = useMemo(() => {
    return toolEvents
      .filter((event) => event.event_type === "tool.completed" || event.event_type === "tool.failed")
      .map((event) => ({
        id: event.id,
        name: String(event.parsedPayload?.skill ?? "unknown"),
        runtimeType: String(event.parsedPayload?.runtime_type ?? "unknown"),
        isBuiltin: Boolean(event.parsedPayload?.is_builtin ?? false),
        summary: String(event.parsedPayload?.summary ?? event.parsedPayload?.error ?? ""),
      }));
  }, [toolEvents]);

  const canCancel = Boolean(run && !["completed", "failed", "cancelled"].includes(run.status));

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Run Detail</h1>
        <div className="flex gap-3 text-sm">
          <Link href="/skills" className="text-blue-400 underline hover:text-blue-300">Skills</Link>
          <Link href="/" className="text-blue-400 underline hover:text-blue-300">Back to dashboard</Link>
        </div>
      </div>

      {isLoading ? <p className="text-sm text-slate-300">Loading run details...</p> : null}
      {error ? <p className="rounded border border-red-600 bg-red-950/40 p-3 text-sm text-red-200">{error}</p> : null}

      {run ? (
        <section className="space-y-3 rounded-lg border border-slate-700 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-medium">Run summary</h2>
            <div className="flex gap-2">
              {canCancel ? (
                <button type="button" onClick={onCancel} disabled={isMutating} className="rounded border border-amber-500 px-3 py-1 text-sm text-amber-200 disabled:opacity-60">
                  {run.cancel_requested ? "Cancel requested" : "Cancel run"}
                </button>
              ) : null}
            </div>
          </div>
          <p className="text-sm">Run ID: {run.id}</p>
          <p className="text-sm">Status: {run.status}</p>
          <p className="text-sm">Task: {run.task}</p>
          <p className="text-sm">Execution mode: {run.execution_mode}</p>
          <p className="text-sm">Planning source: {run.planning_source}</p>
          <p className="text-sm">Planning summary: {run.planning_summary}</p>
          {run.fallback_reason ? <p className="text-sm">Fallback reason: {run.fallback_reason}</p> : null}
          <p className="text-sm">Provider: {run.provider}</p>
          <p className="text-sm">Model: {run.model}</p>
          <p className="text-sm">Synthesis mode: {run.synthesis_mode ?? "n/a"}</p>
          <p className="text-sm">Synthesis status: {run.synthesis_status ?? "n/a"}</p>
          <p className="text-sm">Budget config: {JSON.stringify(run.budget_config ?? {})}</p>
          <p className="text-sm">Budget usage: {JSON.stringify(run.budget_usage_summary ?? {})}</p>
          <p className="text-sm">Evidence summary: {JSON.stringify(run.evidence_summary ?? {})}</p>
          {run.pending_approval ? (
            <div className="rounded border border-yellow-700 bg-yellow-950/40 p-3 text-sm text-yellow-100">
              <p className="font-medium">Waiting for approval</p>
              <p>{run.pending_approval.reason}</p>
              <div className="mt-3 flex gap-2">
                <button type="button" onClick={onApprove} disabled={isMutating} className="rounded bg-green-700 px-3 py-1 text-sm disabled:opacity-60">Approve</button>
                <button type="button" onClick={onDeny} disabled={isMutating} className="rounded bg-red-700 px-3 py-1 text-sm disabled:opacity-60">Deny</button>
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {planningEvents.length > 0 ? (
        <section className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Planning summary</h2>
          <ul className="space-y-2 text-sm text-slate-300">
            {planningEvents.map((event) => (
              <li key={event.id} className="rounded border border-slate-800 p-3">
                <p>{event.event_type}</p>
                <p className="text-xs text-slate-400">{JSON.stringify(event.parsedPayload ?? {}, null, 2)}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {skillSummaries.length > 0 ? (
        <section className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Skill executions</h2>
          <ul className="space-y-2 text-sm text-slate-300">
            {skillSummaries.map((item) => (
              <li key={item.id} className="rounded border border-slate-800 p-3">
                <p>{item.name}</p>
                <p className="text-xs text-slate-400">Runtime: {item.runtimeType} | {item.isBuiltin ? "built-in" : "installed"}</p>
                <p className="text-xs text-slate-400">{item.summary || "No summary"}</p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {run ? (
        <section className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Final output</h2>
          <pre className="whitespace-pre-wrap text-sm text-slate-200">{run.final_output ?? "(pending)"}</pre>
        </section>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2">
        <article className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Tool summary</h2>
          <p className="text-sm text-slate-300">Tool events: {toolEvents.length}</p>
          <ul className="list-disc pl-5 text-xs text-slate-300">
            {toolEvents.slice(0, 6).map((event) => (
              <li key={event.id}>{event.event_type}</li>
            ))}
          </ul>
        </article>

        <article className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Synthesis summary</h2>
          <p className="text-sm text-slate-300">Synthesis events: {synthesisEvents.length}</p>
          <p className="text-xs text-slate-400">Mode: {run?.synthesis_mode ?? "n/a"}. Status: {run?.synthesis_status ?? "n/a"}.</p>
        </article>
      </section>

      <section className="space-y-2 rounded-lg border border-slate-700 p-4">
        <h2 className="text-lg font-medium">Trace timeline</h2>
        {trace.length === 0 ? <p className="text-sm text-slate-400">No trace events recorded.</p> : null}
        <ol className="space-y-2">
          {trace.map((event) => (
            <li key={event.id} className="rounded border border-slate-800 p-3">
              <p className="text-sm font-medium">{event.event_type}</p>
              <p className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()}</p>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300">{JSON.stringify(event.parsedPayload ?? event.payload, null, 2)}</pre>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
