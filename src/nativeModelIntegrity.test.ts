import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { verifyNativeModelHash } from "./nativeModelCatalog";

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: vi.fn(),
  invoke: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());

describe("M3-24 explicit model hash verification", () => {
  it("does not expose filesystem hashing to a browser", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(verifyNativeModelHash("loras/style.safetensors")).rejects.toThrow("Tauri");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("rejects path traversal and unsupported formats before invoking Rust", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    for (const id of ["../secret.safetensors", "loras/../secret.safetensors",
      "loras\\secret.safetensors", "loras/style.ckpt",
      "loras/C:secret.safetensors", "other/a.safetensors", "loras/a/b.safetensors"]) {
      await expect(verifyNativeModelHash(id)).rejects.toThrow("식별자");
    }
    expect(invoke).not.toHaveBeenCalled();
  });

  it.each(["match", "mismatch", "not_recorded"] as const)(
    "calls only the constrained native command for %s",
    async status => {
      vi.mocked(isTauri).mockReturnValue(true);
      vi.mocked(invoke).mockResolvedValue({ status });
      const id = "checkpoints/model.safetensors";
      await expect(verifyNativeModelHash(id)).resolves.toEqual({ status });
      expect(invoke).toHaveBeenCalledExactlyOnceWith("verify_local_model_hash", { modelId: id });
    },
  );

  it("rejects unexpected or malformed native verdicts", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    for (const value of [null, {}, { status: "gpu_verified" }]) {
      vi.mocked(invoke).mockResolvedValueOnce(value);
      await expect(verifyNativeModelHash("vae/vae.safetensors")).rejects.toThrow("형식");
    }
  });
});
