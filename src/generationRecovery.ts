import type { JobSnapshot } from "./nativeGenerationJobs";

export type GenerationFailureCode =
  | "cuda_out_of_memory"
  | "python_dependency_missing"
  | "cuda_runtime_error"
  | "inference_failed"
  | "process_cleanup_failed"
  | "image_verification_failed"
  | "execution_timeout"
  | "user_cancelled";

export type RecoveryAdvice = {
  title: string;
  explanation: string;
  nextStep: string;
  offerSafePreset: boolean;
};

const RECOVERY: Record<GenerationFailureCode, RecoveryAdvice> = {
  cuda_out_of_memory: {
    title: "GPU VRAM 부족",
    explanation: "이미지 생성 중 GPU 메모리가 부족했습니다. 작업이 종료됐는지 확인하세요.",
    nextStep: "GPU를 사용하는 다른 앱을 닫고 512×512·15스텝으로 낮춘 뒤 VRAM 재검사를 실행하세요.",
    offerSafePreset: true,
  },
  python_dependency_missing: {
    title: "Python 패키지 누락",
    explanation: "로컬 추론에 필요한 Python 패키지가 없는 것으로 분류됐습니다.",
    nextStep: "프로젝트의 .venv와 추론 선택 패키지 설치를 확인하고 CUDA 환경 진단을 다시 실행하세요.",
    offerSafePreset: false,
  },
  cuda_runtime_error: {
    title: "CUDA 환경 오류",
    explanation: "GPU 드라이버나 CUDA 지원 PyTorch 초기화에 문제가 발생했습니다.",
    nextStep: "GPU 드라이버와 CUDA 지원 PyTorch를 확인하고 GPU 환경 진단을 다시 실행하세요.",
    offerSafePreset: false,
  },
  inference_failed: {
    title: "이미지 생성 실패",
    explanation: "추론이 정상 완료되지 않았지만 구체적인 원인을 확정할 수 없습니다.",
    nextStep: "SDXL 체크포인트와 로컬 구성, Python 설치를 확인하세요. 자동으로 재실행하지 않습니다.",
    offerSafePreset: false,
  },
  process_cleanup_failed: {
    title: "프로세스 정리 확인 실패",
    explanation: "Python 생성 작업의 하위 프로세스 종료를 확인하지 못했습니다.",
    nextStep: "Windows 작업 관리자에서 생성 관련 프로세스가 남아 있는지 확인하세요. 안전을 위해 GPU 작업을 차단했으므로 정리 상태를 확인하고 앱을 다시 시작하세요.",
    offerSafePreset: false,
  },
  image_verification_failed: {
    title: "결과 이미지 검증 실패",
    explanation: "생성 파일을 정상적인 PNG로 확인하지 못했거나 체크섬·크기가 일치하지 않습니다.",
    nextStep: "디스크 여유 공간과 로컬 생성 폴더를 확인하세요. 문제가 있는 파일은 성공 결과로 취급하지 않습니다.",
    offerSafePreset: false,
  },
  execution_timeout: {
    title: "최대 실행 시간 초과",
    explanation: "허용된 실행 시간을 초과해 종료를 요청했습니다.",
    nextStep: "하위 프로세스가 종료됐는지 확인하고, 필요한 경우 512×512·15스텝으로 낮춰 새 검사를 수행하세요.",
    offerSafePreset: true,
  },
  user_cancelled: {
    title: "사용자가 작업을 취소함",
    explanation: "사용자 요청으로 생성 중지를 시도했습니다.",
    nextStep: "작업 종료 상태를 확인한 다음, 필요하다면 별도로 새 생성에 동의해 주세요.",
    offerSafePreset: false,
  },
};

/** Only static, allowlisted advice enters the UI; raw stderr/paths stay private. */
export function describeGenerationFailure(
  job: Pick<JobSnapshot, "phase" | "failure_code"> | null,
): RecoveryAdvice | null {
  if (!job || !["failed", "timed_out", "cancelled"].includes(job.phase)) return null;
  const fallback: GenerationFailureCode = job.phase === "timed_out"
    ? "execution_timeout" : job.phase === "cancelled"
      ? "user_cancelled" : "inference_failed";
  const code = job.failure_code;
  const safe = code && Object.prototype.hasOwnProperty.call(RECOVERY, code)
    ? code as GenerationFailureCode : fallback;
  return RECOVERY[safe];
}

/** Never return arbitrary subprocess errors or secret local paths to the UI. */
export function explainGenerationStartError(error: unknown): string {
  const value = typeof error === "string" ? error :
    error instanceof Error ? error.message : "";
  const normalized = value.toLowerCase();
  // A failed Windows process-group drain is a session safety lockout,
  // NOT a memory/preset warning and not a transient concurrent job.
  if (normalized.includes("프로세스 종료를 검증하지 못") ||
      normalized.includes("하위 프로세스 정리를 검증하지 못") ||
      normalized.includes("작업 관리자에서 프로세스를 확인")) {
    return "이전 GPU 생성 또는 CUDA 진단의 하위 프로세스 종료를 확인하지 못해 추가 GPU 작업을 차단했습니다. Windows 작업 관리자에서 남아 있는 프로세스를 확인한 후 앱을 다시 시작하세요.";
  }
  if (normalized.includes("vram") || normalized.includes("메모리") ||
      normalized.includes("cuda 사전 검사")) {
    return "GPU 메모리 또는 CUDA 사전 검사로 실행하지 않았습니다. VRAM 재검사로 상태를 확인하고 512×512 권장 설정을 사용해 보세요.";
  }
  if (normalized.includes("already") || normalized.includes("이미") ||
      normalized.includes("진단이 진행") || normalized.includes("진행 중")) {
    return "다른 GPU 생성 또는 진단이 진행 중입니다. 해당 작업이 종료된 후 다시 시도하세요.";
  }
  // A Python spawn error can contain a model filename in its path.
  // Prefer the explicit executable failure over a generic "model" substring.
  if (normalized.includes("python") || normalized.includes(".venv")) {
    return "로컬 Python 추론 환경을 실행할 수 없습니다. 프로젝트의 .venv와 추론 패키지를 확인하세요.";
  }
  if (normalized.includes("sdxl") || normalized.includes("checkpoint") ||
      normalized.includes("config") || normalized.includes("model")) {
    return "SDXL 모델 정보 또는 로컬 설정이 준비되지 않았습니다. 모델 관리와 오프라인 설정을 확인하세요.";
  }
  return "로컬 실행 전 검사에 실패했습니다. GPU 진단과 모델 설정을 확인하세요. 생성은 시작하지 않았습니다.";
}
