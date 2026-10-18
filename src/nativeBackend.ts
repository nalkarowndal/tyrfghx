import { invoke, isTauri } from '@tauri-apps/api/core';
import type { StudioStatus } from './api';

export async function bundledBackendEnabled(): Promise<boolean> {
  return isTauri() && await invoke<boolean>('bundled_backend_enabled');
}

export async function restartBackend(): Promise<StudioStatus> {
  if (!isTauri()) throw new Error('Desktop backend required');
  return invoke<StudioStatus>('restart_backend');
}
