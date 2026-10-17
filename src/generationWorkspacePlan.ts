import type { ModelRecord } from "./api";

export type ImageSettings = {
  checkpointId: string;
  prompt: string;
  negativePrompt: string;
  width: number;
  height: number;
  steps: number;
  guidance: number;
  seed: number;
};
export const DEFAULT_IMAGE_SETTINGS: ImageSettings = {
  checkpointId: "", prompt: "", negativePrompt: "",
  width: 768, height: 768, steps: 20, guidance: 7, seed: 42,
};
export type GenerationPreflight =
  | { ok: true; summary: string; warnings: string[] }
  | { ok: false; summary: string; warnings: string[] };

export function preflightImageSettings(settings: ImageSettings, models: ModelRecord[]): GenerationPreflight {
  const warnings: string[] = [];
  const model = models.find(x => x.id === settings.checkpointId);
  if (!model || model.category !== "checkpoint" ||
      model.file_format !== "safetensors" || model.validation !== "metadata_only") {
    return { ok: false, summary: "유효한 Safetensors 체크포인트를 선택해야 합니다.", warnings };
  }
  if (model.family !== "sdxl") {
    return { ok: false, summary: "M3-1 CLI는 SDXL 계열만 대상으로 합니다.", warnings };
  }
  if (!settings.prompt.trim() || settings.prompt.length > 2000 || settings.negativePrompt.length > 2000) {
    return { ok: false, summary: "프롬프트는 1~2000자, 제외 프롬프트는 2000자 이하로 입력하세요.", warnings };
  }
  if (![settings.width, settings.height].every(n => Number.isInteger(n) && n >= 512 && n <= 1024 && n % 64 === 0)) {
    return { ok: false, summary: "크기 값은 512~1024 사이의 64배수여야 합니다.", warnings };
  }
  if (!Number.isInteger(settings.steps) || settings.steps < 1 || settings.steps > 40 ||
      !Number.isFinite(settings.guidance) || settings.guidance < 1 || settings.guidance > 12 ||
      !Number.isInteger(settings.seed) || settings.seed < 0 || settings.seed > 4294967295) {
    return { ok: false, summary: "스텝(1~40), CFG(1~12), 시드(0~4294967295)를 확인하세요.", warnings };
  }
  if (model.family_source === "manual") {
    warnings.push("SDXL 계열은 사용자가 지정한 정보입니다. 실제 아키텍처는 검증되지 않았습니다.");
  }
  if (settings.width > 768 || settings.height > 768) {
    warnings.push("8GB GPU에서는 높은 해상도로 인해 VRAM 부족이 발생할 수 있습니다.");
  }
  warnings.push("이 화면은 CUDA, 로컬 설정 파일, 실제 모델 호환성 및 이미지 생성 가능 여부를 검사하지 않습니다.");
  return { ok: true, summary: "입력값 및 모델 메타데이터 사전 검사 통과 (GPU 실행 검증 아님)", warnings };
}
