import type { ModelRecord } from "./api";
import { hasCurrentCatalogConsent } from "./catalogConsent";
import { describe, expect, it } from "vitest";

const checkpoint: ModelRecord = {
  id: "checkpoints/test.safetensors", name: "test.safetensors",
  category: "checkpoint", file_format: "safetensors", size_bytes: 100,
  validation: "metadata_only", reported_architecture: null, note: "",
  display_name: null, family: "sdxl", family_source: "manual",
  license: null, notes: null, integrity_state: "snapshot_unchanged",
  recorded_sha256: null, potential_duplicate_ids: [],
};

describe("M3-28 GPU consent must be tied to a catalog snapshot", () => {
  it("accepts only explicit consent for the same current nonempty catalog", () => {
    const list = [checkpoint];
    expect(hasCurrentCatalogConsent(list, list, false, "")).toBe(true);
    expect(hasCurrentCatalogConsent(null, list, false, "")).toBe(false);
    expect(hasCurrentCatalogConsent([], [], false, "")).toBe(false);
  });

  it("rejects a refreshed copy even with the same checkpoint ID and metadata", () => {
    const previous = [checkpoint];
    const replaced = [{ ...checkpoint }];
    expect(replaced[0].id).toBe(previous[0].id);
    expect(hasCurrentCatalogConsent(previous, replaced, false, "")).toBe(false);
  });

  it("rejects consent during refresh and after any catalog read error", () => {
    const list = [checkpoint];
    expect(hasCurrentCatalogConsent(list, list, true, "")).toBe(false);
    expect(hasCurrentCatalogConsent(list, list, false, "catalog unavailable")).toBe(false);
    expect(hasCurrentCatalogConsent(list, [], true, "")).toBe(false);
  });

  it("requires new consent on the recovered list, not old consent", () => {
    const before = [checkpoint];
    const after = [checkpoint];
    expect(hasCurrentCatalogConsent(before, after, false, "")).toBe(false);
    expect(hasCurrentCatalogConsent(after, after, false, "")).toBe(true);
  });
});
