/** Thin typed wrapper over the FastAPI service. */

import type {
  JobStatus,
  ManagementPreset,
  ParameterPayload,
  ProfileRecord,
  ScenarioConfig,
  SimulationResults,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}: ${body.slice(0, 300)}`);
  }
  return (await response.json()) as T;
}

export const api = {
  defaultScenario: () => request<ScenarioConfig>("/api/scenarios/default"),
  parameters: (model: "formind" | "grassmind") =>
    request<ParameterPayload>(`/api/parameters/${model}`),
  managementPresets: () => request<ManagementPreset[]>("/api/management/presets"),
  submit: (config: ScenarioConfig) =>
    request<JobStatus>("/api/simulations", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  status: (id: string) => request<JobStatus>(`/api/simulations/${id}`),
  results: (id: string) => request<SimulationResults>(`/api/simulations/${id}/results`),
  profile: (id: string, x: number, y: number) =>
    request<ProfileRecord[]>(`/api/simulations/${id}/profile?x=${x}&y=${y}`),
};

/**
 * Poll a job to completion.
 *
 * Job-and-poll rather than a streamed response because a century-scale run takes
 * tens of seconds; `onProgress` receives the real day count from inside the
 * simulation loop, not an estimate.
 */
export async function runToCompletion(
  config: ScenarioConfig,
  onProgress: (status: JobStatus) => void,
  intervalMs = 400,
): Promise<{ results: SimulationResults; status: JobStatus }> {
  const job = await api.submit(config);
  onProgress(job);
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    const status = await api.status(job.id);
    onProgress(status);
    if (status.state === "failed") throw new Error(status.error ?? "simulation failed");
    if (status.state === "done") {
      return { results: await api.results(job.id), status };
    }
  }
}
