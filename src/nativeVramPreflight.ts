import { invoke, isTauri } from "@tauri-apps/api/core";

export type VramReason =
  | "total_vram_under_6gib"
  | "free_vram_under_4gib"
  | "high_resolution_on_8gib";

export type VramTrialAssessment = {
  status: "trial_allowed" | "blocked_by_default";
  reasons: VramReason[];
  total_vram_bytes: number;
  free_vram_bytes_at_check: number;
  requested_width: number;
  requested_height: number;
  suggested_width: number;
  suggested_height: number;
  suggested_steps: number;
};

/** No model, prompt, executable or file-path argument is accepted by the command. */
export async function inspectVramTrial(width: number, height: number): Promise<VramTrialAssessment> {
  if (!isTauri()) throw new Error("VRAM 사전 검사는 Tauri 데스크톱에서만 사용할 수 있습니다.");
  if (![width, height].every(v =>
    Number.isSafeInteger(v) && v >= 512 && v <= 1024 && v % 64 === 0
  )) throw new Error("지원하지 않는 이미지 크기입니다.");
  return invoke<VramTrialAssessment>("check_local_generation_vram", {
    request: { width, height },
  });
}

export const vramReasonLabels: Record<VramReason, string> = {
  total_vram_under_6gib: "GPU 전체 VRAM이 6GiB 미만입니다.",
  free_vram_under_4gib: "현재 가용 VRAM이 4GiB 미만입니다. 다른 GPU 프로그램을 종료하세요.",
  high_resolution_on_8gib: "8GiB 이하 GPU에서 요청 해상도가 768×768보다 큽니다.",
};
