import { useState } from "react";
import { inspectVramTrial, vramReasonLabels, type VramTrialAssessment } from "./nativeVramPreflight";

const GIB = 1024 ** 3;

export default function VramPreflightPanel({
  supported, busy, width, height, onApplySafe,
}: {
  supported: boolean;
  busy: boolean;
  width: number;
  height: number;
  onApplySafe: () => void;
}) {
  const [checking, setChecking] = useState(false);
  const [assessment, setAssessment] = useState<VramTrialAssessment | null>(null);
  const [error, setError] = useState("");

  async function inspect() {
    if (!supported || busy || checking) return;
    setChecking(true);
    setError("");
    setAssessment(null);
    try {
      setAssessment(await inspectVramTrial(width, height));
    } catch (problem) {
      setError(String(problem));
    } finally {
      setChecking(false);
    }
  }

  return <section aria-label="생성 전 VRAM 사전 검사" className="vram-preflight-panel">
    <div className="generation-heading">
      <h3>현재 해상도로 VRAM 사전 검사</h3>
      <button type="button" className="refresh-button" onClick={inspect}
        disabled={!supported || busy || checking}>
        {checking ? "CUDA 검사 중..." : "VRAM 재검사"}
      </button>
    </div>
    <p className="muted">선택한 {width}×{height} 해상도로 생성해도 되는지 현재 CUDA 가용 메모리를 조회합니다. 모델을 로드하지 않으며 실제 이미지 생성은 시작하지 않습니다.</p>
    {!supported && <p className="muted">Windows Tauri 개발판에서만 VRAM 사전 검사가 가능합니다.</p>}
    {busy && <p className="muted">GPU 생성 또는 다른 작업이 진행 중이면 검사를 시작할 수 없습니다.</p>}
    {error && <div role="alert" className="model-error">
      <strong>VRAM 검사 실패</strong>
      <p>{error}</p>
      <p>로컬 Python·CUDA 드라이버·GPU 환경을 확인하고 다시 검사하세요. 생성 가능 판정을 내리지 않았습니다.</p>
    </div>}
    {assessment && <div role="status" className="compatibility-result">
      <strong>{assessment.status === "trial_allowed"
        ? "현재 메모리 기준에서 시험 생성 시도 가능"
        : "현재 메모리 기준에서 기본적으로 생성 차단"}</strong>
      <p>GPU 전체: {(assessment.total_vram_bytes / GIB).toFixed(2)} GiB
        {" · "}검사 시 가용: {(assessment.free_vram_bytes_at_check / GIB).toFixed(2)} GiB</p>
      {assessment.reasons.map(reason => <p key={reason}>{vramReasonLabels[reason] ?? "메모리 위험 기준을 확인하세요."}</p>)}
      {assessment.status === "blocked_by_default" && <>
        <p>VRAM을 사용하는 다른 앱을 종료한 뒤 다시 검사하거나 512×512로 낮춰 보세요. 여전히 부족할 수 있습니다.</p>
        {(width !== assessment.suggested_width || height !== assessment.suggested_height) &&
          <button type="button" className="refresh-button"
            onClick={onApplySafe} disabled={busy || checking}>
            권장 {assessment.suggested_width}×{assessment.suggested_height} 설정 적용
          </button>}
      </>}
      <p>권장 초기 설정: {assessment.suggested_width}×{assessment.suggested_height},
        {" "}{assessment.suggested_steps}스텝, 1장.</p>
      <p><strong>이 결과는 해당 순간의 측정치입니다.</strong> 실제 생성 시작 시 다시 검사하며, 검사 통과는 모델 로딩·생성 성공을 보장하지 않습니다.</p>
    </div>}
  </section>;
}
