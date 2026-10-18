import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { inspectVramTrial, vramReasonLabels } from "./nativeVramPreflight";

vi.mock("@tauri-apps/api/core", () => ({
  isTauri: vi.fn(), invoke: vi.fn(),
}));
afterEach(() => vi.resetAllMocks());

describe("M3-13 read-only native VRAM recovery preflight", () => {
  it("does not permit browser-side CUDA checks", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(inspectVramTrial(512, 512)).rejects.toThrow("Tauri");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("sends only width and height to one fixed native command", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    const report = {
      status: "blocked_by_default", reasons: ["free_vram_under_4gib"],
      total_vram_bytes: 8589934592, free_vram_bytes_at_check: 3221225472,
      requested_width: 512, requested_height: 512,
      suggested_width: 512, suggested_height: 512, suggested_steps: 15,
    };
    vi.mocked(invoke).mockResolvedValue(report);
    await expect(inspectVramTrial(512, 512)).resolves.toEqual(report);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("check_local_generation_vram", {
      request: { width: 512, height: 512 },
    });
    expect(JSON.stringify(vi.mocked(invoke).mock.calls)).not.toContain("python.exe");
  });

  it("rejects unsupported dimensions without starting an OS subprocess", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    await expect(inspectVramTrial(512, 513)).rejects.toThrow("크기");
    await expect(inspectVramTrial(2048, 1024)).rejects.toThrow("크기");
    await expect(inspectVramTrial(Number.NaN, 512)).rejects.toThrow("크기");
    expect(invoke).not.toHaveBeenCalled();
  });

  it("explains each blocked memory condition without claiming compatibility", () => {
    expect(vramReasonLabels.free_vram_under_4gib).toContain("프로그램");
    expect(vramReasonLabels.high_resolution_on_8gib).toContain("768×768");
    expect(vramReasonLabels.total_vram_under_6gib).toContain("6GiB");
  });
});
