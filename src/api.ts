export type EngineStatus = { name: string; status: "unavailable" | "ready"; note: string };
export type StudioStatus = { app: string; version: string; mode: string; engines: EngineStatus[] };
export const API_URL = "http://127.0.0.1:8765";
export async function getStatus(signal?: AbortSignal): Promise<StudioStatus> {
  const response = await fetch(`${API_URL}/api/status`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<StudioStatus>;
}

export type ModelRecord = {
  id: string;
  name: string;
  category: "checkpoint" | "lora" | "vae";
  file_format: "safetensors" | "ckpt";
  size_bytes: number;
  reported_architecture: string | null;
  validation: "metadata_only" | "invalid_header" | "blocked_legacy";
  note: string;
};

export async function getModels(signal?: AbortSignal): Promise<ModelRecord[]> {
  const response = await fetch(`${API_URL}/api/models`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<ModelRecord[]>;
}
