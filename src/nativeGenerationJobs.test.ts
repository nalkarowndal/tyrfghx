import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { DEFAULT_IMAGE_SETTINGS } from "./generationWorkspacePlan";
import { startLocalGeneration, getGenerationJobStatus, cancelLocalGeneration } from "./nativeGenerationJobs";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(), invoke: vi.fn() }));
afterEach(() => vi.resetAllMocks());

describe("M3-3 local generation permissions", () => {
  const settings = { ...DEFAULT_IMAGE_SETTINGS, checkpointId: "checkpoints/a.safetensors", prompt: "forest" };
  it("disallows browser execution without IPC", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(startLocalGeneration(settings, true)).rejects.toThrow("데스크톱");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("requires a fresh explicit consent", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    await expect(startLocalGeneration(settings, false)).rejects.toThrow("동의");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("uses allowlisted IPC command with typed args and never an executable path", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({ job_id: 1, phase: "running", message: "started" });
    await startLocalGeneration(settings, true);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("start_local_generation", {
      request: {
        checkpointId: "checkpoints/a.safetensors",
        prompt: "forest", negativePrompt: "", width: 768, height: 768,
        steps: 20, guidance: 7, seed: 42, confirmed: true,
      },
    });
  });
  it("reads current status and cancels only a valid job identifier", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({ job_id: 7, phase: "cancelled", message: "stopped" });
    await getGenerationJobStatus();
    await cancelLocalGeneration(7);
    expect(invoke).toHaveBeenNthCalledWith(1, "generation_job_status");
    expect(invoke).toHaveBeenNthCalledWith(2, "cancel_local_generation", { jobId: 7 });
    await expect(cancelLocalGeneration(-1)).rejects.toThrow("ID");
    expect(invoke).toHaveBeenCalledTimes(2);
  });
});
