import { describe, expect, it } from "vitest";
import { describeGenerationFailure, explainGenerationStartError } from "./generationRecovery";

describe("M3-14 safe GPU failure recovery messages", () => {
  it("presents a conservative preset only for GPU OOM and timeout", () => {
    const oom = describeGenerationFailure({
      phase: "failed", failure_code: "cuda_out_of_memory",
    });
    expect(oom?.offerSafePreset).toBe(true);
    expect(oom?.nextStep).toContain("512×512");
    const timeout = describeGenerationFailure({ phase: "timed_out", failure_code: undefined });
    expect(timeout?.offerSafePreset).toBe(true);
    const dependency = describeGenerationFailure({
      phase: "failed", failure_code: "python_dependency_missing",
    });
    expect(dependency?.offerSafePreset).toBe(false);
  });

  it("requires manual inspection and app restart after process cleanup failure", () => {
    const advice = describeGenerationFailure({
      phase: "failed", failure_code: "process_cleanup_failed",
    });
    expect(advice?.offerSafePreset).toBe(false);
    expect(advice?.nextStep).toContain("작업 관리자");
    expect(advice?.nextStep).toContain("다시 시작");
  });

  it("does not treat success, an unrecognized code or cancellation as OOM", () => {
    expect(describeGenerationFailure({
      phase: "succeeded", failure_code: undefined,
    })).toBeNull();
    expect(describeGenerationFailure({
      phase: "failed", failure_code: "malicious_native_path" as never,
    })?.title).toBe("이미지 생성 실패");
    expect(describeGenerationFailure({
      phase: "cancelled", failure_code: "user_cancelled",
    })?.offerSafePreset).toBe(false);
  });

  it("never repeats executable paths or arbitrary private process errors", () => {
    const secret = String.raw`C:\Users\private\secret_model.safetensors`;
    const text = explainGenerationStartError(`Could not start python at ${secret}`);
    expect(text).not.toContain(secret);
    expect(text).toContain("Python");
    const fallback = explainGenerationStartError({ message: secret });
    expect(fallback).not.toContain(secret);
    expect(fallback).toContain("시작하지 않았습니다");
  });

  it("prioritizes a persistent cleanup lockout over ordinary GPU failures", () => {
    const text = explainGenerationStartError(
      "이전 CUDA 진단의 Windows 프로세스 종료를 검증하지 못했습니다. 작업 관리자에서 프로세스를 확인하세요."
    );
    expect(text).toContain("추가 GPU 작업을 차단");
    expect(text).toContain("다시 시작");
    expect(text).not.toContain("512×512");
    const protectedPath = String.raw`C:\Users\private\model.safetensors`;
    const other = explainGenerationStartError(
      `GPU 진단 종료 후 Windows 하위 프로세스 정리를 검증하지 못했습니다 ${protectedPath}`
    );
    expect(other).not.toContain(protectedPath);
    expect(other).toContain("앱을 다시 시작");
  });

  it("maps CUDA preflight and concurrency problems to non-executing guidance", () => {
    expect(explainGenerationStartError("GPU VRAM 4GiB 미만")).toContain("VRAM 재검사");
    expect(explainGenerationStartError("Another generation job is already running")).toContain("다른");
  });
});
