import { describe, expect, it } from "vitest";
import { generationPolicyMessage, type GenerationPolicyState } from "./generationSupportPolicy";

describe("M3-31 native release-mode policy attestation", () => {
  it("distinguishes an actual native disabled verdict from a pending command", () => {
    expect(generationPolicyMessage("disabled")).toBe("로컬 GPU 실행 정책 확인됨: 배포판 비활성");
    expect(generationPolicyMessage("checking")).not.toContain("확인됨");
    expect(generationPolicyMessage("error")).not.toContain("확인됨");
  });
  it("never claims verified release policy for a browser or failed IPC", () => {
    expect(generationPolicyMessage("browser")).toContain("브라우저에서는 비활성");
    expect(generationPolicyMessage("error")).toContain("실행 차단");
  });
  it("requires consent/safety checks even on supported debug builds", () => {
    expect(generationPolicyMessage("enabled")).toContain("사용자 승인 및 안전 검사 필요");
    const states: GenerationPolicyState[] = ["checking", "enabled", "disabled", "error", "browser"];
    expect(new Set(states.map(generationPolicyMessage)).size).toBe(states.length);
  });
});
