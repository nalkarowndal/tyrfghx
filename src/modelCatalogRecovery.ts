import type { ModelRecord } from "./api";

/** Safe, fixed user-facing error. Native Rust and local HTTP failures may contain private paths. */
export const MODEL_CATALOG_RETRY_MESSAGE =
  "모델 목록을 불러오지 못했습니다. 로컬 모델 폴더와 연결 상태를 확인한 뒤 목록 새로고침으로 다시 시도하세요.";

export type CatalogEvents = {
  isCurrent: () => boolean;
  onStart: () => void;
  onLoaded: (models: ModelRecord[]) => void;
  onFailed: (safeMessage: string) => void;
  onFinished: () => void;
};

const textOrNull = (value: unknown): boolean =>
  value === null || (typeof value === "string" && value.length <= 2_000);

function isSupportedModelRecord(value: unknown): value is ModelRecord {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<ModelRecord>;
  return typeof item.id === "string" && item.id.length > 0 && item.id.length <= 512
    && typeof item.name === "string" && item.name.length > 0 && item.name.length <= 512
    && ["checkpoint", "lora", "vae"].includes(item.category ?? "")
    && ["safetensors", "ckpt"].includes(item.file_format ?? "")
    && ["metadata_only", "invalid_header", "blocked_legacy"].includes(item.validation ?? "")
    && typeof item.size_bytes === "number" && Number.isSafeInteger(item.size_bytes)
    && item.size_bytes >= 0
    && typeof item.note === "string" && item.note.length <= 2_000
    && textOrNull(item.reported_architecture)
    && textOrNull(item.display_name)
    && (item.family === null || ["sd15", "sd2", "sdxl", "sd3", "flux"].includes(item.family ?? ""))
    && ["manual", "header", "unknown"].includes(item.family_source ?? "")
    && textOrNull(item.license) && textOrNull(item.notes)
    && ["not_recorded", "snapshot_unchanged", "file_changed"].includes(item.integrity_state ?? "")
    && textOrNull(item.recorded_sha256)
    && Array.isArray(item.potential_duplicate_ids)
    && item.potential_duplicate_ids.length <= 3_000
    && item.potential_duplicate_ids.every(id => typeof id === "string" && id.length <= 512);
}

/**
 * Fail-closed catalog loading for either Tauri IPC or the local Python API.
 *
 * A request becoming stale (navigation, refresh, StrictMode cleanup) must
 * never repopulate models or modify loading state. On loading/failure the
 * caller clears its old catalog, so previously valid checkpoints cannot be
 * used after a refresh failure. Never retry automatically or log native errors.
 */
export async function loadModelCatalog(
  request: () => Promise<ModelRecord[]>,
  events: CatalogEvents,
): Promise<void> {
  if (!events.isCurrent()) return;
  events.onStart();
  try {
    const models: unknown = await request();
    if (!events.isCurrent()) return;
    if (!Array.isArray(models) || models.length > 3_000
        || !models.every(isSupportedModelRecord)) {
      throw new Error("invalid_catalog_payload");
    }
    events.onLoaded(models);
  } catch {
    if (events.isCurrent()) events.onFailed(MODEL_CATALOG_RETRY_MESSAGE);
  } finally {
    if (events.isCurrent()) events.onFinished();
  }
}
