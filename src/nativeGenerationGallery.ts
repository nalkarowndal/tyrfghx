import { invoke, isTauri } from "@tauri-apps/api/core";

export type GenerationPreview = { id: string; image_src: string; size_bytes: number };

/** Returns only whitelisted bounded local PNG previews; never receives a filesystem path. */
export async function getNativeGenerationPreviews(): Promise<GenerationPreview[]> {
  if (!isTauri()) throw new Error("Tauri 데스크톱에서만 결과 이미지를 확인할 수 있습니다.");
  return invoke<GenerationPreview[]>("list_generation_previews");
}
