import { invoke } from '@tauri-apps/api/core';
import { bundledBackendEnabled } from './nativeBackend';

export type EngineStatus = { name: string; status: "unavailable" | "ready"; note: string };
export type RuntimePackage = {
  package: string;
  state: "detected" | "missing" | "unknown";
  version: string | null;
};
export type RuntimeSetupPlan = {
  schema_version: 1;
  inspection_scope: "current_api_python_process_only";
  inference_runtime_connection: "not_connected";
  recommended_isolation: "separate_python_virtual_environment";
  preferred_python_version: "3.12";
  installation_mode: "manual_only";
  automatic_downloads_enabled: false;
  automated_package_installation: false;
  gpu_probe_authorized: false;
  cuda_or_device_compatibility_verified: false;
  model_execution_verified: false;
  torch_wheel_hint: {
    kind: "cuda_wheel_metadata" | "cpu_wheel_metadata" | "unknown";
    tag: string | null;
    hardware_compatibility_verified: false;
  };
  setup_steps: string[];
  documentation: {
    python_venv: string;
    pytorch_windows: string;
  };
};
export type RuntimePreflight = {
  schema_version: number;
  setup_plan?: RuntimeSetupPlan;
  method: "distribution_metadata_only";
  readiness: "not_verified";
  cuda_tested: false;
  gpu_accessed: false;
  models_opened: false;
  downloads_performed: false;
  packages: RuntimePackage[];
};
export type StudioStatus = {
  app: string;
  version: string;
  mode: string;
  engines: EngineStatus[];
  runtime_preflight?: RuntimePreflight;
};
export const API_URL = "http://127.0.0.1:8765";
export async function getStatus(signal?: AbortSignal): Promise<StudioStatus> {
  if (await bundledBackendEnabled()) {
    // Managed failures must never connect to an unrelated service on port 8765.
    return invoke<StudioStatus>('backend_status');
  }
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
  display_name: string | null;
  family: "sd15" | "sd2" | "sdxl" | "sd3" | "flux" | null;
  family_source: "manual" | "header" | "unknown";
  license: string | null;
  notes: string | null;
  integrity_state: "not_recorded" | "snapshot_unchanged" | "file_changed";
  recorded_sha256: string | null;
  potential_duplicate_ids: string[];
};

export async function getModels(signal?: AbortSignal): Promise<ModelRecord[]> {
  const response = await fetch(`${API_URL}/api/models`, { signal });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<ModelRecord[]>;
}

export type CompatibilityReport = {
  status: "possible_match" | "family_mismatch" | "unknown" | "blocked" | "not_found" | "invalid_selection";
  checkpoint_id: string;
  lora_id: string;
  summary: string;
};
export async function getCompatibility(checkpointId: string, loraId: string): Promise<CompatibilityReport> {
  const params = new URLSearchParams({ checkpoint_id: checkpointId, lora_id: loraId });
  const response = await fetch(`${API_URL}/api/models/compatibility?${params.toString()}`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<CompatibilityReport>;
}
