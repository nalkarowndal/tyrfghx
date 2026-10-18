/**
 * Native runner availability is distinct from a merely disabled launch button.
 * A launch button can be disabled because no checkpoint/consent exists, even
 * when a development build actually supports GPU inference.
 */
export type GenerationPolicyState = "checking" | "enabled" | "disabled" | "error" | "browser";

export function generationPolicyMessage(state: GenerationPolicyState): string {
  switch (state) {
    case "checking":
      return "로컬 GPU 실행 정책: 네이티브 명령 확인 중";
    case "enabled":
      return "로컬 GPU 실행 정책 확인됨: 개발판 실행 가능 (사용자 승인 및 안전 검사 필요)";
    case "disabled":
      return "로컬 GPU 실행 정책 확인됨: 배포판 비활성";
    case "error":
      return "로컬 GPU 실행 정책 확인 실패: 실행 차단";
    case "browser":
      return "로컬 GPU 실행 정책: 브라우저에서는 비활성";
  }
}
