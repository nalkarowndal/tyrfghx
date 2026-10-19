import { isTauri, invoke } from "@tauri-apps/api/core";

export type ImportCategory = "checkpoints" | "loras" | "vae";
export type NativeImportResult = {
  model_id: string;
  sha256: string;
  size_bytes: number;
};

/** User selects the source in Rust's native dialog. No input file path crosses IPC. */
export async function importModelFromNativeDialog(category: ImportCategory): Promise<NativeImportResult | null> {
  if (!isTauri()) throw new Error("데스크톱 Tauri 앱에서만 사용할 수 있습니다.");
  return invoke<NativeImportResult | null>("import_local_model", { category });
}
