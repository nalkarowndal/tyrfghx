import { describe, expect, it } from "vitest";
import type { ModelRecord } from "./api";
import { loadModelCatalog, MODEL_CATALOG_RETRY_MESSAGE, type CatalogEvents } from "./modelCatalogRecovery";

function fixture(id = "checkpoints/example.safetensors"): ModelRecord {
  return {
    id, name: "example.safetensors", category: "checkpoint", file_format: "safetensors",
    size_bytes: 1024, validation: "metadata_only", reported_architecture: null, note: "",
    display_name: null, family: "sdxl", family_source: "header", license: null,
    notes: null, integrity_state: "not_recorded", recorded_sha256: null,
    potential_duplicate_ids: [],
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function stateHarness() {
  let current = true;
  const state = { models: [fixture()], loading: false, error: "", events: [] as string[] };
  const events: CatalogEvents = {
    isCurrent: () => current,
    onStart: () => {
      state.events.push("start");
      state.models = [];
      state.error = "";
      state.loading = true;
    },
    onLoaded: models => {
      state.events.push("loaded");
      state.models = models;
      state.error = "";
    },
    onFailed: safe => {
      state.events.push("failed");
      state.models = [];
      state.error = safe;
    },
    onFinished: () => {
      state.events.push("finished");
      state.loading = false;
    },
  };
  return { state, events, invalidate: () => { current = false; } };
}

describe("M3-27 model catalog recovery", () => {
  it("clears cached checkpoints immediately while refreshing", async () => {
    const h = stateHarness();
    const task = deferred<ModelRecord[]>();
    const waiting = loadModelCatalog(() => task.promise, h.events);
    expect(h.state.models).toEqual([]);
    expect(h.state.loading).toBe(true);
    task.resolve([fixture("checkpoints/new.safetensors")]);
    await waiting;
    expect(h.state.models.map(x => x.id)).toEqual(["checkpoints/new.safetensors"]);
    expect(h.state.events).toEqual(["start", "loaded", "finished"]);
  });

  it("never displays raw native file paths and never reuses old models after failure", async () => {
    const h = stateHarness();
    await loadModelCatalog(
      () => Promise.reject(new Error("C:\\Users\\Private\\models\\weights.safetensors: permission denied")),
      h.events,
    );
    expect(h.state.models).toEqual([]);
    expect(h.state.loading).toBe(false);
    expect(h.state.error).toBe(MODEL_CATALOG_RETRY_MESSAGE);
    expect(h.state.error).not.toContain("Private");
    expect(h.state.events).toEqual(["start", "failed", "finished"]);
  });

  it("ignores superseded responses even when old Tauri IPC cannot be aborted", async () => {
    const h = stateHarness();
    const task = deferred<ModelRecord[]>();
    const waiting = loadModelCatalog(() => task.promise, h.events);
    h.invalidate();
    task.resolve([fixture("checkpoints/stale.safetensors")]);
    await waiting;
    expect(h.state.models).toEqual([]);
    expect(h.state.events).toEqual(["start"]);
  });

  it("ignores superseded rejections without warning or clearing a newer view", async () => {
    const h = stateHarness();
    const task = deferred<ModelRecord[]>();
    const waiting = loadModelCatalog(() => task.promise, h.events);
    h.invalidate();
    h.state.models = [fixture("checkpoints/newer.safetensors")];
    task.reject("C:\\private\\path");
    await waiting;
    expect(h.state.models[0]?.id).toBe("checkpoints/newer.safetensors");
    expect(h.state.events).toEqual(["start"]);
  });

  it("rejects malformed and oversized catalogs rather than rendering unsafe entries", async () => {
    for (const payload of [null, {}, [null], [{ id: "/tmp/private" }],
      [{ ...fixture(), potential_duplicate_ids: null }],
      [{ ...fixture(), family: "untrusted_value" }],
      [{ ...fixture(), size_bytes: Number.NaN }],
      Array(3001).fill(fixture())]) {
      const h = stateHarness();
      await loadModelCatalog(
        () => Promise.resolve(payload as ModelRecord[]),
        h.events,
      );
      expect(h.state.error).toBe(MODEL_CATALOG_RETRY_MESSAGE);
      expect(h.state.models).toEqual([]);
    }
  });

  it("explicit manual retry recovers cleanly after a failure", async () => {
    const h = stateHarness();
    await loadModelCatalog(() => Promise.reject(new Error("offline")), h.events);
    expect(h.state.error).toBe(MODEL_CATALOG_RETRY_MESSAGE);
    await loadModelCatalog(() => Promise.resolve([fixture()]), h.events);
    expect(h.state.models).toHaveLength(1);
    expect(h.state.error).toBe("");
    expect(h.state.events).toEqual(["start", "failed", "finished", "start", "loaded", "finished"]);
  });

  it("does not start an already invalidated catalog request", async () => {
    const h = stateHarness();
    h.invalidate();
    await loadModelCatalog(() => { throw new Error("should not call"); }, h.events);
    expect(h.state.events).toEqual([]);
  });
});
