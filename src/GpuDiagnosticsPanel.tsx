import { useState } from "react";
import { inspectNativeGpu, readableGpuStatus, type GpuDiagnosticReport } from "./nativeGpuDiagnostics";

const GIB = 1024 * 1024 * 1024;
function gib(bytes: number): string {
  return (bytes / GIB).toFixed(2) + " GiB";
}

export default function GpuDiagnosticsPanel({ supported, busy }: {
  supported: boolean; busy: boolean;
}) {
  const [report, setReport] = useState<GpuDiagnosticReport | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function check() {
    if (!supported || busy || pending) return;
    setPending(true);
    setReport(null);
    setError("");
    try {
      setReport(await inspectNativeGpu());
    } catch (reason) {
      setError(String(reason));
    } finally {
      setPending(false);
    }
  }

  return <section className="gpu-diagnostics-panel" aria-label="GPU 환경 진단">
    <div className="generation-heading">
      <h3>GPU 환경 확인</h3>
      <button type="button" className="refresh-button" onClick={check} disabled={!supported || busy || pending}>
        {pending ? "진단 중..." : "GPU 진단 실행"}
      </button>
    </div>
    <p className="muted">모델을 불러오지 않고 CUDA·PyTorch 설치와 사용 가능한 VRAM을 확인합니다. GPU 초기화는 발생할 수 있으며, 실제 이미지 생성 테스트는 아닙니다.</p>
    {!supported && <p className="muted">Windows Tauri 개발판에서만 진단할 수 있습니다. 다른 환경에서는 로컬 <code>backend/gpu_diagnostics.py</code>를 직접 실행하세요.</p>}
    {busy && <p className="muted">이미지 생성 작업 중에는 GPU 진단을 시작할 수 없습니다.</p>}
    {error && <p role="alert" className="model-error">{error}</p>}
    {report && <div role="status" className="compatibility-result">
      <strong>{readableGpuStatus(report.status)}</strong>
      <p>PyTorch: {report.torch_version ?? "미설치 또는 확인 불가"} / CUDA 빌드: {report.torch_cuda_build ?? "없음"}</p>
      {report.gpu && <>
        <p>GPU: {report.gpu.name} (연산 기능 {report.gpu.compute_capability})</p>
        <p>VRAM 전체: {gib(report.gpu.total_vram_bytes)} / 진단 시 가용: {gib(report.gpu.free_vram_bytes_at_check)}</p>
      </>}
      <p>초기 테스트 권장: {report.trial_settings.width}×{report.trial_settings.height}, {report.trial_settings.steps}스텝, {report.trial_settings.images}장, CPU 오프로딩</p>
      {report.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
      <p><strong>CUDA 장치 인식은 SDXL 모델 로딩이나 생성 성공을 보장하지 않습니다.</strong></p>
    </div>}
  </section>;
}
