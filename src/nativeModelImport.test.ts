import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { importModelFromNativeDialog } from "./nativeModelImport";

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}));

afterEach(() => vi.resetAllMocks());

describe("Tauri local model import", () => {
  it("refuses browser imports without touching IPC", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(importModelFromNativeDialog("loras")).rejects.toThrow("Tauri");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("passes a model category only, never a filesystem path", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({
      model_id: "loras/style.safetensors",
      sha256: "a".repeat(64),
      size_bytes: 1024,
    });
    const response = await importModelFromNativeDialog("loras");
    expect(invoke).toHaveBeenCalledExactlyOnceWith("import_local_model", { category: "loras" });
    expect(response?.model_id).toBe("loras/style.safetensors");
  });

  it("preserves cancellation as null", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue(null);
    expect(await importModelFromNativeDialog("vae")).toBeNull();
  });
});
