import { describe, expect, it } from "vitest";
import type { ModelRecord } from "./api";
import { DEFAULT_IMAGE_SETTINGS, preflightImageSettings } from "./generationWorkspacePlan";

const checkpoint: ModelRecord = {
  id: "checkpoints/test.safetensors", name: "test.safetensors", category: "checkpoint",
  file_format: "safetensors", size_bytes: 512, reported_architecture: "stable-diffusion-xl-v1-base",
  validation: "metadata_only", note: "", display_name: null, family: "sdxl",
  family_source: "header", license: null, notes: null,
  integrity_state: "not_recorded", recorded_sha256: null, potential_duplicate_ids: [],
};
const valid = { ...DEFAULT_IMAGE_SETTINGS, checkpointId: checkpoint.id, prompt: "watercolor mountains" };
describe("M3-2 generation preflight (not GPU availability)", () => {
  it("validates eligible SDXL parameters without claiming model load success", () => {
    const result = preflightImageSettings(valid, [checkpoint]);
    expect(result.ok).toBe(true);
    expect(result.warnings.join(" ")).toContain("검사하지 않습니다");
  });
  it("rejects invalid checkpoint and unsupported family", () => {
    expect(preflightImageSettings(valid, []).ok).toBe(false);
    expect(preflightImageSettings(valid, [{ ...checkpoint, family: "sd15" }]).ok).toBe(false);
    expect(preflightImageSettings(valid, [{ ...checkpoint, validation: "invalid_header" }]).ok).toBe(false);
  });
  it("rejects out-of-range settings", () => {
    expect(preflightImageSettings({ ...valid, steps: 41 }, [checkpoint]).ok).toBe(false);
    expect(preflightImageSettings({ ...valid, width: 777 }, [checkpoint]).ok).toBe(false);
    expect(preflightImageSettings({ ...valid, seed: -1 }, [checkpoint]).ok).toBe(false);
    expect(preflightImageSettings({ ...valid, guidance: Number.NaN }, [checkpoint]).ok).toBe(false);
    expect(preflightImageSettings({ ...valid, prompt: "" }, [checkpoint]).ok).toBe(false);
  });
  it("calls out a manual family hint and high VRAM usage", () => {
    const result = preflightImageSettings({ ...valid, width: 1024 }, [{ ...checkpoint, family_source: "manual" }]);
    expect(result.ok).toBe(true);
    expect(result.warnings).toHaveLength(3);
  });
});
