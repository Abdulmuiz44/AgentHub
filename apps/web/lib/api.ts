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

export type ProviderSummary = {
  provider: ProviderCapability;
  configuration_status: string;
  is_configured: boolean;
};

export type ProviderModelsItem = {
  provider_name: string;
  display_name: string;
  configuration_status: string;
  is_configured: boolean;
  models: string[];
};

export type ProviderModelsResponse = {
  providers: ProviderModelsItem[];
};

export type ProviderHealthResponse = {
  provider: string;
  configuration_status: string;
  healthy: boolean;
  message: string;
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

export async function listProviders(): Promise<ProviderSummary[]> {
  const response = await fetch(`${API_BASE}/providers`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Provider list request failed");
  }
  return response.json();
}

export async function listProviderModels(provider: string): Promise<ProviderModelsItem> {
  const response = await fetch(`${API_BASE}/providers/models?provider=${encodeURIComponent(provider)}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    await readError(response, "Provider models request failed");
  }

  const payload: ProviderModelsResponse = await response.json();
  const providerMatch = payload.providers.find((item) => item.provider_name === provider);
  if (!providerMatch) {
    throw new Error(`Provider not found: ${provider}`);
  }
  return providerMatch;
}

export async function checkProviderHealth(provider: string): Promise<ProviderHealthResponse> {
  const response = await fetch(`${API_BASE}/providers/health-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider }),
  });
  if (!response.ok) {
    await readError(response, "Provider health check request failed");
  }
  return response.json();
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
