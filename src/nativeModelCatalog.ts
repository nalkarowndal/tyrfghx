import { invoke, isTauri } from "@tauri-apps/api/core";
import type { CompatibilityReport, ModelRecord } from "./api";

export async function getNativeModels(): Promise<ModelRecord[]> {
  if (!isTauri()) throw new Error("Tauri 데스크톱에서만 사용할 수 있습니다.");
  return invoke<ModelRecord[]>("list_local_models");
}

/**
 * Desktop-only *metadata hint*: it is NOT a GPU load or LoRA tensor compatibility test.
 * Mirrors the local Python read-only preflight classifications.
 */
export function compareNativeModels(
  models: ModelRecord[], checkpointId: string, loraId: string,
): CompatibilityReport {
  const checkpoint = models.find(x => x.id === checkpointId);
  const lora = models.find(x => x.id === loraId);
  let status: CompatibilityReport["status"];
  let summary: string;
  if (!checkpoint || !lora) {
    status = "not_found";
    summary = "선택된 모델 파일이 현재 목록에 없습니다.";
  } else if (checkpoint.category !== "checkpoint" || lora.category !== "lora") {
    status = "invalid_selection";
    summary = "체크포인트와 LoRA를 각각 선택해야 합니다.";
  } else if (checkpoint.validation !== "metadata_only" || lora.validation !== "metadata_only") {
    status = "blocked";
    summary = "헤더 오류 또는 안전하지 않은 형식의 파일이 포함되어 있습니다.";
  } else if (!checkpoint.family || !lora.family) {
    status = "unknown";
    summary = "계열 정보가 충분하지 않아 사전 일치 여부를 판단할 수 없습니다.";
  } else if (checkpoint.family !== lora.family) {
    status = "family_mismatch";
    summary = "모델 계열이 서로 다릅니다. 로딩 전 추가 확인이 필요합니다.";
  } else {
    status = "possible_match";
    summary = "메타데이터상 모델 계열이 같습니다. 실제 호환성 및 GPU 실행은 미검증입니다.";
  }
  return { checkpoint_id: checkpointId, lora_id: loraId, status, summary };
}
