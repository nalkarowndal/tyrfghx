import { afterEach, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { getNativeGenerationPreviews } from "./nativeGenerationGallery";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(), invoke: vi.fn() }));
afterEach(() => vi.resetAllMocks());

it("blocks browser access to native previews", async () => {
  vi.mocked(isTauri).mockReturnValue(false);
  await expect(getNativeGenerationPreviews()).rejects.toThrow("Tauri");
  expect(invoke).not.toHaveBeenCalled();
});
it("uses a read-only command without filesystem path parameters", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue([]);
  await expect(getNativeGenerationPreviews()).resolves.toEqual([]);
  expect(invoke).toHaveBeenCalledExactlyOnceWith("list_generation_previews");
});
