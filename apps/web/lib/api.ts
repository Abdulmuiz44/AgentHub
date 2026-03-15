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
  synthesis_error_summary?: string | null;
  execution_summary?: Record<string, unknown>;
  evidence_summary?: Record<string, unknown>;
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

export type SkillConfigField = {
  key: string;
  label?: string | null;
  description?: string | null;
  required: boolean;
  secret: boolean;
  value_type: string;
  default?: unknown;
  env_var_allowed: boolean;
  example?: string | null;
};

export type SkillConfigValue = {
  key: string;
  value?: unknown;
  configured: boolean;
  secret_binding?: string | null;
  uses_environment_binding: boolean;
};

export type SkillConfigState = {
  readiness_status: string;
  readiness_summary: string;
  values: SkillConfigValue[];
};

export type SkillResponse = {
  id?: number | null;
  name: string;
  version: string;
  description: string;
  runtime_type: string;
  enabled: boolean;
  is_builtin: boolean;
  scopes: string[];
  tags: string[];
  install_source?: string | null;
  last_test_status?: string | null;
  last_test_summary?: string | null;
  last_tested_at?: string | null;
  readiness_status: string;
  readiness_summary: string;
  config_schema: SkillConfigField[];
  config_state: SkillConfigState;
  manifest: Record<string, unknown>;
};

export type SkillConfigResponse = {
  skill_name: string;
  config_schema: SkillConfigField[];
  state: SkillConfigState;
  updated_at?: string | null;
};

export type SkillInstallPayload = {
  manifest?: Record<string, unknown>;
  manifest_path?: string;
};

export type SkillConfigUpdatePayload = {
  values?: Record<string, unknown>;
  secret_bindings?: Record<string, string>;
};

export type SkillTestResponse = {
  skill: SkillResponse;
  status: string;
  summary: string;
  checked_at: string;
  metadata: Record<string, unknown>;
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
  const response = await fetch(`${API_BASE}/providers/models?provider=${encodeURIComponent(provider)}`, { cache: "no-store" });
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

export async function listSkills(): Promise<SkillResponse[]> {
  const response = await fetch(`${API_BASE}/skills`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Skill list request failed");
  }
  return response.json();
}

export async function getSkillConfig(name: string): Promise<SkillConfigResponse> {
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(name)}/config`, { cache: "no-store" });
  if (!response.ok) {
    await readError(response, "Skill config request failed");
  }
  return response.json();
}

export async function installSkill(payload: SkillInstallPayload): Promise<SkillResponse> {
  const response = await fetch(`${API_BASE}/skills/install`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await readError(response, "Skill install request failed");
  }
  return response.json();
}

export async function updateSkillConfig(name: string, payload: SkillConfigUpdatePayload): Promise<SkillResponse> {
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(name)}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    await readError(response, "Skill config update request failed");
  }
  return response.json();
}

export async function setSkillEnabled(name: string, enabled: boolean): Promise<SkillResponse> {
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(name)}/${enabled ? "enable" : "disable"}`, { method: "POST" });
  if (!response.ok) {
    await readError(response, "Skill enable/disable request failed");
  }
  return response.json();
}

export async function testSkill(name: string): Promise<SkillTestResponse> {
  const response = await fetch(`${API_BASE}/skills/${encodeURIComponent(name)}/test`, { method: "POST" });
  if (!response.ok) {
    await readError(response, "Skill test request failed");
  }
  return response.json();
}
