import { invoke, isTauri } from "@tauri-apps/api/core";

export type GpuDetails = {
  index: number;
  name: string;
  compute_capability: string;
  total_vram_bytes: number;
  free_vram_bytes_at_check: number;
};
export type GpuDiagnosticReport = {
  schema_version: 1;
  status: "ready_for_trial" | "torch_missing" | "torch_import_error" |
    "cpu_only_torch" | "unsupported_backend" | "cuda_unavailable" |
    "cuda_probe_error" | "unavailable";
  os: string;
  torch_version: string | null;
  torch_cuda_build: string | null;
  gpu: GpuDetails | null;
  warnings: string[];
  trial_settings: {
    width: number; height: number; steps: number; images: number; cpu_offload: boolean;
  };
};

/** Fixed-command, read-only CUDA readiness check. No filesystem or model paths. */
export async function inspectNativeGpu(): Promise<GpuDiagnosticReport> {
  if (!isTauri()) throw new Error("GPU 환경 진단은 Tauri 데스크톱 개발판에서만 가능합니다.");
  return invoke<GpuDiagnosticReport>("inspect_local_gpu");
}

export function readableGpuStatus(status: GpuDiagnosticReport["status"]): string {
  const names: Record<GpuDiagnosticReport["status"], string> = {
    ready_for_trial: "CUDA 장치 인식됨 — 생성 가능 여부는 미검증",
    torch_missing: "PyTorch가 설치되지 않았습니다",
    torch_import_error: "PyTorch 초기화 실패",
    cpu_only_torch: "CPU 전용 PyTorch 빌드",
    unsupported_backend: "지원하지 않는 GPU 백엔드",
    cuda_unavailable: "CUDA를 사용할 수 없습니다",
    cuda_probe_error: "CUDA 정보 조회 실패",
    unavailable: "진단 정보를 사용할 수 없습니다",
  };
  return names[status];
}
