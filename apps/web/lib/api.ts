export type CreateRunPayload = {
  task: string;
  provider: string;
  model: string;
  session_id?: number;
  enabled_skills?: string[];
};

export type RunResponse = {
  id: number;
  session_id: number;
  task: string;
  provider: string;
  model: string;
  status: string;
  created_at: string;
};

export type TraceResponse = {
  id: number;
  run_id: number;
  event_type: string;
  payload: string;
  created_at: string;
};

export type CreateRunResult = {
  run: RunResponse;
  trace_events: TraceResponse[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function createRun(payload: CreateRunPayload): Promise<CreateRunResult> {
  const response = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Run creation failed (${response.status}): ${body}`);
  }

  return response.json();
}
