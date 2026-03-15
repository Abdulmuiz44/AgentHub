"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { RunResponse, TraceResponse, fetchRunDetail, fetchRunTrace } from "../../../lib/api";

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
        if (!active) {
          return;
        }
        setRun(runDetail);
        setTrace(traceItems.map((item) => ({ ...item, parsedPayload: parsePayload(item.payload) })));
      } catch (loadError) {
        if (!active) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Failed to load run detail.");
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [runId]);

  const toolEvents = useMemo(
    () => trace.filter((event) => event.event_type.startsWith("tool.")),
    [trace]
  );
  const synthesisEvents = useMemo(
    () => trace.filter((event) => event.event_type.startsWith("synth")),
    [trace]
  );
  const fetchedSources = useMemo(() => {
    const urls: string[] = [];
    for (const event of trace) {
      const output = event.parsedPayload?.output as Record<string, unknown> | undefined;
      const pages = output?.fetched_pages as Array<Record<string, unknown>> | undefined;
      if (!pages) continue;
      for (const page of pages) {
        const url = String(page.url ?? "").trim();
        if (url && !urls.includes(url)) {
          urls.push(url);
        }
      }
    }
    return urls;
  }, [trace]);

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold">Run Detail</h1>
        <Link href="/" className="text-sm text-blue-400 underline hover:text-blue-300">
          Back to dashboard
        </Link>
      </div>

      {isLoading ? <p className="text-sm text-slate-300">Loading run details...</p> : null}
      {error ? <p className="rounded border border-red-600 bg-red-950/40 p-3 text-sm text-red-200">{error}</p> : null}

      {run ? (
        <section className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Run summary</h2>
          <p className="text-sm">Run ID: {run.id}</p>
          <p className="text-sm">Status: {run.status}</p>
          <p className="text-sm">Task: {run.task}</p>
          <p className="text-sm">Provider: {run.provider}</p>
          <p className="text-sm">Model: {run.model}</p>
          <p className="text-sm">Synthesis mode: {run.synthesis_mode ?? "n/a"}</p>
          <p className="text-sm">Synthesis status: {run.synthesis_status ?? "n/a"}</p>
          <p className="text-sm">Evidence summary: {JSON.stringify(run.evidence_summary ?? {})}</p>
        </section>
      ) : null}

      {run ? (
        <section className="space-y-2 rounded-lg border border-slate-700 p-4">
          <h2 className="text-lg font-medium">Final output</h2>
          <pre className="whitespace-pre-wrap text-sm text-slate-200">{run.final_output ?? "(none)"}</pre>
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
        <h2 className="text-lg font-medium">Fetched sources</h2>
        {fetchedSources.length === 0 ? <p className="text-sm text-slate-400">No fetched web sources recorded.</p> : null}
        <ul className="list-disc pl-5 text-xs text-slate-300">
          {fetchedSources.map((url) => (
            <li key={url}>{url}</li>
          ))}
        </ul>
      </section>

      <section className="space-y-2 rounded-lg border border-slate-700 p-4">
        <h2 className="text-lg font-medium">Trace timeline</h2>
        {trace.length === 0 ? <p className="text-sm text-slate-400">No trace events recorded.</p> : null}
        <ol className="space-y-2">
          {trace.map((event) => (
            <li key={event.id} className="rounded border border-slate-800 p-3">
              <p className="text-sm font-medium">{event.event_type}</p>
              <p className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()}</p>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-300">
                {JSON.stringify(event.parsedPayload ?? event.payload, null, 2)}
              </pre>
            </li>
          ))}
        </ol>
      </section>
    </main>
  );
}
