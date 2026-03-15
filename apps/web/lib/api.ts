export type CreateRunPayload = {
  task: string;
  provider: string;
  model: string;
  session_id?: number;
  enabled_skills?: string[];
  execute_now?: boolean;
};

export type RunResponse = {
  id: number;
  session_id: number;
  task: string;
  provider: string;
  model: string;
  status: string;
  final_output?: string | null;
  synthesis_mode?: string | null;
  synthesis_status?: string | null;
  created_at: string;
  updated_at: string;
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

export type ProviderCapability = {
  name: string;
  display_name: string;
  models: string[];
  supports_streaming: boolean;
};

export type ProviderHealthResponse = {
  provider: string;
  healthy: boolean;
  message?: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function readError(response: Response, fallback: string): Promise<never> {
  const body = await response.text();
  throw new Error(`${fallback} (${response.status}): ${body}`);
}

export async function createRun(payload: CreateRunPayload): Promise<CreateRunResult> {
  const response = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    await readError(response, "Run creation failed");
  }

  return response.json();
}

export async function listProviders(): Promise<ProviderCapability[]> {
  const response = await fetch(`${API_BASE}/providers`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Provider list request failed");
  }
  return response.json();
}

export async function listProviderModels(provider: string): Promise<string[]> {
  const providers = await listProviders();
  const providerMatch = providers.find((item) => item.name === provider);
  if (!providerMatch) {
    throw new Error(`Provider not found: ${provider}`);
  }
  return providerMatch.models;
}

export async function checkProviderHealth(provider: string): Promise<ProviderHealthResponse> {
  try {
    const healthResponse = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!healthResponse.ok) {
      return { provider, healthy: false, message: `API health check failed (${healthResponse.status})` };
    }
    const providers = await listProviders();
    const exists = providers.some((item) => item.name === provider);
    if (!exists) {
      return { provider, healthy: false, message: `Provider not found: ${provider}` };
    }
    return { provider, healthy: true, message: "API healthy and provider registered" };
  } catch (error) {
    return {
      provider,
      healthy: false,
      message: error instanceof Error ? error.message : "Provider health check failed",
    };
  }
}

export async function fetchRunDetail(runId: number): Promise<RunResponse> {
  const response = await fetch(`${API_BASE}/runs/${runId}`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Run detail request failed");
  }
  return response.json();
}

export async function fetchRunTrace(runId: number): Promise<TraceResponse[]> {
  const response = await fetch(`${API_BASE}/runs/${runId}/trace`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Run trace request failed");
  }
  return response.json();
}
