import { describe, expect, it } from "vitest";
import { belongsToActiveCatalogRequest } from "./catalogRequestGate";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe("M3-28 delayed native IPC must not revive obsolete model verdicts", () => {
  it("accepts a result only for the matching catalog and click request", () => {
    expect(belongsToActiveCatalogRequest(10, 2, 10, 2)).toBe(true);
    expect(belongsToActiveCatalogRequest(10, 2, 11, 2)).toBe(false);
    expect(belongsToActiveCatalogRequest(10, 2, 10, 3)).toBe(false);
  });

  it("drops a late successful checksum after catalog refresh", async () => {
    let catalog = 1;
    let request = 1;
    let shown: string | null = null;
    const task = deferred<string>();
    const pending = task.promise.then(status => {
      if (belongsToActiveCatalogRequest(1, 1, catalog, request)) shown = status;
    });
    catalog += 1;
    request += 1;
    task.resolve("match");
    await pending;
    expect(shown).toBeNull();
  });

  it("drops a late failed compatibility request after selection change", async () => {
    let catalog = 3;
    let request = 4;
    let shown: string | null = null;
    const task = deferred<string>();
    const pending = task.promise.catch(() => {
      if (belongsToActiveCatalogRequest(3, 4, catalog, request)) shown = "error";
    });
    request += 1;
    task.reject(new Error("C:\\Private\\model.safetensors"));
    await pending;
    expect(shown).toBeNull();
    expect(belongsToActiveCatalogRequest(3, 5, catalog, request)).toBe(true);
  });

  it("only a new request on a recovered catalog can update the UI", () => {
    expect(belongsToActiveCatalogRequest(1, 3, 2, 4)).toBe(false);
    expect(belongsToActiveCatalogRequest(2, 4, 2, 4)).toBe(true);
  });
});
