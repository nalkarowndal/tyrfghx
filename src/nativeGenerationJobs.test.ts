import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { DEFAULT_IMAGE_SETTINGS } from "./generationWorkspacePlan";
import { startLocalGeneration, getGenerationJobStatus, cancelLocalGeneration, isLocalGenerationSupported } from "./nativeGenerationJobs";

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
        acknowledgeVramRisk: false,
      },
    });
  });
  it("requires a separate explicit boolean for VRAM safety override", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue({ job_id: 2, phase: "running" });
    await startLocalGeneration(settings, true, true);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("start_local_generation", {
      request: expect.objectContaining({
        confirmed: true, acknowledgeVramRisk: true,
      }),
    });
    expect(JSON.stringify(vi.mocked(invoke).mock.calls)).not.toContain("python.exe");
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

it("reads the native release/dev feature gate instead of assuming all Tauri builds run GPU jobs", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue(false);
  await expect(isLocalGenerationSupported()).resolves.toBe(false);
  expect(invoke).toHaveBeenCalledExactlyOnceWith("local_generation_supported");
});

it("shows a timed-out terminal phase without treating it as success", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue({
    job_id: 12, phase: "timed_out",
    message: "Maximum runtime exceeded",
    elapsed_seconds: 1800, time_limit_seconds: 1800,
  });
  const state = await getGenerationJobStatus();
  expect(state.phase).toBe("timed_out");
  expect(state.elapsed_seconds).toBe(state.time_limit_seconds);
});

it("exposes only the allowlisted verification metadata, not a raw output path", async () => {
  vi.mocked(isTauri).mockReturnValue(true);
  vi.mocked(invoke).mockResolvedValue({
    job_id: 3, phase: "succeeded", message: "Checksum verified",
    elapsed_seconds: 19, time_limit_seconds: 1800,
    result: {
      file_name: "aiimage-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png",
      png_sha256: "b".repeat(64), seed: 42, elapsed_seconds: 16.5,
      peak_allocated_bytes: 3_000_000_000,
      peak_reserved_bytes: 3_200_000_000,
      measurement: "torch_cuda_allocator", validation: "png_decoded_and_sha256_verified",
      width: 512, height: 512,
    },
  });
  const state = await getGenerationJobStatus();
  expect(state.result?.validation).toBe("png_decoded_and_sha256_verified");
  expect(state.result?.peak_allocated_bytes).toBe(3_000_000_000);
  expect([state.result?.width, state.result?.height]).toEqual([512, 512]);
  expect(JSON.stringify(state.result)).not.toContain("C:\\");
});
