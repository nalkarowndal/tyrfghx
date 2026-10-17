export type EngineStatus = { name: string; status: "unavailable" | "ready"; note: string };
export type StudioStatus = { app: string; version: string; mode: string; engines: EngineStatus[] };
export const API_URL = "http://127.0.0.1:8765";
export async function getStatus(signal?: AbortSignal): Promise<StudioStatus> {
  const response = await fetch(`${API_URL}/api/status`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<StudioStatus>;
}
