import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import type { ModelRecord } from "./api";
import { compareNativeModels, getNativeModels } from "./nativeModelCatalog";

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());

function record(id: string, category: ModelRecord["category"], family: ModelRecord["family"], validation: ModelRecord["validation"] = "metadata_only"): ModelRecord {
  return {
    id, name: id.split("/")[1], category, family, validation,
    file_format: "safetensors", size_bytes: 512,
    reported_architecture: null, note: "Header only", display_name: null,
    family_source: family ? "manual" : "unknown", license: null,
    notes: null, integrity_state: "not_recorded", recorded_sha256: null,
    potential_duplicate_ids: [],
  };
}

const checkpoint = record("checkpoints/base.safetensors", "checkpoint", "sdxl");
const lora = record("loras/style.safetensors", "lora", "sdxl");

describe("offline native model catalog", () => {
  it("refuses a browser-only IPC call", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(getNativeModels()).rejects.toThrow("Tauri");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("invokes read-only catalog with no filesystem path arguments", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue([checkpoint]);
    expect(await getNativeModels()).toEqual([checkpoint]);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("list_local_models");
  });

  it("distinguishes a possible family match from a GPU compatibility guarantee", () => {
    const report = compareNativeModels([checkpoint, lora], checkpoint.id, lora.id);
    expect(report.status).toBe("possible_match");
    expect(report.summary).toContain("미검증");
  });

  it("reports unknown, mismatch, blocked, and invalid selection", () => {
    const cases = [
      [record(lora.id, "lora", null), "unknown"],
      [record(lora.id, "lora", "sd15"), "family_mismatch"],
      [record(lora.id, "lora", "sdxl", "invalid_header"), "blocked"],
      [record(lora.id, "vae", "sdxl"), "invalid_selection"],
    ] as const;
    for (const [candidate, status] of cases) {
      expect(compareNativeModels([checkpoint, candidate], checkpoint.id, lora.id).status).toBe(status);
    }
    expect(compareNativeModels([checkpoint], checkpoint.id, lora.id).status).toBe("not_found");
  });
});
