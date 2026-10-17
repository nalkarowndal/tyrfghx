import { invoke, isTauri } from "@tauri-apps/api/core";
import type { ImageSettings } from "./generationWorkspacePlan";

export type JobPhase = "idle" | "running" | "cancelling" | "succeeded" | "failed" | "cancelled" | "timed_out";
export type VerifiedGeneration = {
  file_name: string;
  png_sha256: string;
  seed: number;
  elapsed_seconds: number;
  peak_allocated_bytes: number | null;
  peak_reserved_bytes: number | null;
  measurement: "torch_cuda_allocator" | "measurement_failed" | "unavailable";
  validation: "png_signature_and_sha256_verified";
};
export type JobSnapshot = {
  job_id: number;
  phase: JobPhase;
  message: string;
  elapsed_seconds: number;
  time_limit_seconds: number;
  result: VerifiedGeneration | null;
};

/** Windows DEBUG builds only. No paths, executables or arbitrary command names cross IPC. */
export async function startLocalGeneration(settings: ImageSettings, confirmed: boolean): Promise<JobSnapshot> {
  if (!isTauri()) throw new Error("데스크톱 개발판에서만 실행할 수 있습니다.");
  if (!confirmed) throw new Error("GPU 실행에 대한 명시적 동의가 필요합니다.");
  const request = {
    checkpointId: settings.checkpointId,
    prompt: settings.prompt,
    negativePrompt: settings.negativePrompt,
    width: settings.width, height: settings.height,
    steps: settings.steps, guidance: settings.guidance,
    seed: settings.seed, confirmed,
  };
  return invoke<JobSnapshot>("start_local_generation", { request });
}
export async function getGenerationJobStatus(): Promise<JobSnapshot> {
  if (!isTauri()) throw new Error("데스크톱 개발판에서만 조회할 수 있습니다.");
  return invoke<JobSnapshot>("generation_job_status");
}
export async function cancelLocalGeneration(jobId: number): Promise<JobSnapshot> {
  if (!isTauri()) throw new Error("데스크톱 개발판에서만 취소할 수 있습니다.");
  if (!Number.isSafeInteger(jobId) || jobId < 1) throw new Error("유효한 실행 작업 ID가 필요합니다.");
  return invoke<JobSnapshot>("cancel_local_generation", { jobId });
}

export async function isLocalGenerationSupported(): Promise<boolean> {
  if (!isTauri()) return false;
  return invoke<boolean>("local_generation_supported");
}
