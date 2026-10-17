import { afterEach, describe, expect, it, vi } from "vitest";
import { invoke, isTauri } from "@tauri-apps/api/core";
import { inspectNativeGpu, readableGpuStatus, type GpuDiagnosticReport } from "./nativeGpuDiagnostics";

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(), invoke: vi.fn() }));
afterEach(() => vi.resetAllMocks());

const report: GpuDiagnosticReport = {
  schema_version: 1, status: "ready_for_trial", os: "Windows",
  torch_version: "2.9", torch_cuda_build: "12.8",
  gpu: { index: 0, name: "Fixture GPU", compute_capability: "7.5",
    total_vram_bytes: 8589934592, free_vram_bytes_at_check: 6442450944 },
  warnings: ["실제 모델 로딩은 미검증"],
  trial_settings: { width: 512, height: 512, steps: 15, images: 1, cpu_offload: true },
};

describe("M3-7 GPU diagnostics IPC", () => {
  it("never invokes the native command in a browser", async () => {
    vi.mocked(isTauri).mockReturnValue(false);
    await expect(inspectNativeGpu()).rejects.toThrow("Tauri");
    expect(invoke).not.toHaveBeenCalled();
  });
  it("uses a fixed command with no model path, executable, or user arguments", async () => {
    vi.mocked(isTauri).mockReturnValue(true);
    vi.mocked(invoke).mockResolvedValue(report);
    await expect(inspectNativeGpu()).resolves.toEqual(report);
    expect(invoke).toHaveBeenCalledExactlyOnceWith("inspect_local_gpu");
  });
  it("does not present CUDA recognition as image generation success", () => {
    expect(readableGpuStatus("ready_for_trial")).toContain("미검증");
    expect(readableGpuStatus("torch_missing")).toContain("설치");
    expect(readableGpuStatus("cuda_probe_error")).toContain("실패");
  });
});
