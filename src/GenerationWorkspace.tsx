import { useEffect, useMemo, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import GpuDiagnosticsPanel from "./GpuDiagnosticsPanel";
import { describeGenerationFailure, explainGenerationStartError } from "./generationRecovery";
import VramPreflightPanel from "./VramPreflightPanel";
import type { ModelRecord } from "./api";
import { DEFAULT_IMAGE_SETTINGS, preflightImageSettings, type ImageSettings } from "./generationWorkspacePlan";
import { getNativeGenerationPreviews, type GenerationPreview } from "./nativeGenerationGallery";
import { cancelLocalGeneration, getGenerationJobStatus, isLocalGenerationSupported, startLocalGeneration, type JobSnapshot } from "./nativeGenerationJobs";

export default function GenerationWorkspace({ models, loadingModels, modelsError, onRefreshModels }: {
  models: ModelRecord[]; loadingModels: boolean; modelsError: string; onRefreshModels: () => void;
}) {
  const [settings, setSettings] = useState<ImageSettings>(DEFAULT_IMAGE_SETTINGS);
  const [checked, setChecked] = useState(false);
  const [previews, setPreviews] = useState<GenerationPreview[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [galleryError, setGalleryError] = useState("");
  const [galleryRefresh, setGalleryRefresh] = useState(0);
  const [consent, setConsent] = useState(false);
  const [vramRiskConsent, setVramRiskConsent] = useState(false);
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [jobLoading, setJobLoading] = useState(false);
  const [jobError, setJobError] = useState("");
  const [jobStatusLoaded, setJobStatusLoaded] = useState(false);
  const [runnerSupported, setRunnerSupported] = useState(false);
  const desktop = isTauri();
  const eligibleModels = useMemo(() => models.filter(x => x.category === "checkpoint"), [models]);
  const assessment = preflightImageSettings(settings, models);
  const update = (field: keyof ImageSettings, value: string | number) => {
    setSettings(previous => ({ ...previous, [field]: value }));
    setChecked(false);
    setConsent(false);
    setVramRiskConsent(false);
  };

  useEffect(() => {
    if (!desktop) return;
    let cancelled = false;
    setGalleryLoading(true);
    setGalleryError("");
    getNativeGenerationPreviews()
      .then(value => { if (!cancelled) setPreviews(value); })
      .catch(reason => { if (!cancelled) setGalleryError(String(reason)); })
      .finally(() => { if (!cancelled) setGalleryLoading(false); });
    return () => { cancelled = true; };
  }, [desktop, galleryRefresh]);

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    isLocalGenerationSupported()
      .then(value => { if (active) setRunnerSupported(value); })
      .catch(reason => { if (active) setJobError(String(reason)); });
    getGenerationJobStatus()
      .then(value => { if (active) setJob(value); })
      .catch(reason => { if (active) setJobError(String(reason)); })
      .finally(() => { if (active) setJobStatusLoaded(true); });
    return () => { active = false; };
  }, [desktop]);

  useEffect(() => {
    if (!desktop || (job?.phase !== "running" && job?.phase !== "cancelling")) return;
    let active = true;
    const id = window.setInterval(() => {
      getGenerationJobStatus()
        .then(value => { if (active) setJob(value); })
        .catch(reason => { if (active) setJobError(String(reason)); });
    }, 1500);
    return () => { active = false; window.clearInterval(id); };
  }, [desktop, job?.phase]);

  async function startGeneration() {
    if (!desktop || !runnerSupported || !assessment.ok || !consent || jobLoading ||
        !jobStatusLoaded || job?.phase === "running" || job?.phase === "cancelling") return;
    setJobLoading(true);
    setJobError("");
    try {
      const result = await startLocalGeneration(settings, consent, vramRiskConsent);
      setJob(result);
      setConsent(false);
      setVramRiskConsent(false);
    } catch (reason) {
      setJobError(explainGenerationStartError(reason));
    } finally {
      setJobLoading(false);
    }
  }

  async function stopGeneration() {
    if (!job || job.phase !== "running" || jobLoading) return;
    setJobLoading(true);
    setJobError("");
    try {
      setJob(await cancelLocalGeneration(job.job_id));
    } catch (reason) {
      setJobError(String(reason));
    } finally {
      setJobLoading(false);
    }
  }

  // Gallery refresh after a reported success; not evidence of GPU/PNG quality.
  useEffect(() => {
    if (desktop && job?.phase === "succeeded") {
      setGalleryRefresh(n => n + 1);
    }
  }, [desktop, job?.job_id, job?.phase]);

  function applySafeTrial() {
    setSettings(previous => ({ ...previous, width: 512, height: 512, steps: 15 }));
    setChecked(false);
    setConsent(false);
    setVramRiskConsent(false);
    setJobError("");
  }

  const jobBusy = job?.phase === "running" || job?.phase === "cancelling";
  const recoveryAdvice = describeGenerationFailure(job);
  const canRun = desktop && runnerSupported && assessment.ok && consent && jobStatusLoaded && !jobBusy && !jobLoading;
  return <div className="generation-layout">
    <section className="generation-panel" aria-label="이미지 생성 설정">
      <div className="generation-heading"><h2>이미지 생성</h2><span className="generation-tag">M3-14 · 생성 오류 안내</span></div>
      <p className="muted">Windows Tauri 개발판에서는 명시적으로 승인한 한 건의 로컬 SDXL 추론을 시작하거나 중지할 수 있습니다. 배포판과 웹 브라우저에서는 비활성화됩니다.</p>
      <GpuDiagnosticsPanel supported={runnerSupported} busy={jobBusy || jobLoading} />
      <VramPreflightPanel
        key={settings.width + "x" + settings.height}
        supported={runnerSupported} busy={jobBusy || jobLoading}
        width={settings.width} height={settings.height} onApplySafe={applySafeTrial}
      />
      <div className="generation-fields">
        <label>체크포인트
          <select aria-label="생성 체크포인트" value={settings.checkpointId} onChange={e => update("checkpointId", e.target.value)}>
            <option value="">체크포인트 선택</option>
            {eligibleModels.map(x => <option value={x.id} key={x.id}>{x.display_name || x.name} · {x.family || "계열 미확인"}</option>)}
          </select>
        </label>
        <button type="button" className="refresh-button" onClick={onRefreshModels} disabled={loadingModels}>{loadingModels ? "검색 중..." : "모델 목록 새로고침"}</button>
        {modelsError && <p role="alert" className="model-error">모델 목록 오류: {modelsError}</p>}
        <label>프롬프트
          <textarea aria-label="이미지 프롬프트" rows={4} maxLength={2000} value={settings.prompt} placeholder="생성하려는 이미지를 자세히 설명하세요" onChange={e => update("prompt", e.target.value)} />
        </label>
        <label>제외 프롬프트
          <textarea aria-label="제외 프롬프트" rows={2} maxLength={2000} value={settings.negativePrompt} placeholder="피하고 싶은 특징" onChange={e => update("negativePrompt", e.target.value)} />
        </label>
        <div className="generation-row">
          <label>너비
            <select aria-label="이미지 너비" value={settings.width} onChange={e => update("width", Number(e.target.value))}>
              {[512, 640, 768, 896, 1024].map(x => <option value={x} key={x}>{x}</option>)}
            </select>
          </label>
          <label>높이
            <select aria-label="이미지 높이" value={settings.height} onChange={e => update("height", Number(e.target.value))}>
              {[512, 640, 768, 896, 1024].map(x => <option value={x} key={x}>{x}</option>)}
            </select>
          </label>
          <label>스텝 (1~40)
            <input aria-label="생성 스텝" type="number" min={1} max={40} value={settings.steps} onChange={e => update("steps", Number(e.target.value))} />
          </label>
          <label>CFG (1~12)
            <input aria-label="CFG" type="number" min={1} max={12} step={0.5} value={settings.guidance} onChange={e => update("guidance", Number(e.target.value))} />
          </label>
        </div>
        <label>시드 (0~4294967295)
          <input aria-label="이미지 시드" type="number" min={0} max={4294967295} value={settings.seed} onChange={e => update("seed", Number(e.target.value))} />
        </label>
        <label className="generation-consent"><input aria-label="실제 GPU 추론 실행 동의" type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />
          로컬 GPU 연산이 시작되며 VRAM 부족이나 모델 오류가 발생할 수 있음을 확인했습니다.
        </label>
        <p className="muted">GPU 생성 시작 전에 전체 VRAM 6GiB, 가용 VRAM 4GiB, 8GiB 이하 GPU의 해상도 768×768 기준을 다시 확인합니다. 안전 조건을 충족하지 못하면 기본적으로 실행을 차단합니다. 이는 권장 초기 검사 기준이며 성공을 보장하지 않습니다.</p>
        <label className="generation-consent">
          <input aria-label="VRAM 부족 위험 별도 동의" type="checkbox"
            checked={vramRiskConsent} onChange={e => setVramRiskConsent(e.target.checked)} />
          추가 VRAM 위험을 이해했습니다. 메모리 안전 기준에 걸리더라도 실행을 시도하는 데 동의합니다. (권장하지 않음, OOM 가능)
        </label>
        <div className="generation-actions">
          <button type="button" className="refresh-button" onClick={() => setChecked(true)}>입력 사전 검사</button>
          <button type="button" className="refresh-button" onClick={startGeneration} disabled={!canRun}>
            {jobLoading ? "처리 중..." : "GPU 생성 시작 (개발판 전용)"}
          </button>
          <button type="button" onClick={stopGeneration} disabled={job?.phase !== "running" || jobLoading}>생성 취소</button>
        </div>
        {!runnerSupported && <p className="muted">GPU 직접 실행은 Windows Tauri 디버그 개발판에서만 허용됩니다. 브라우저·배포판에서는 CLI를 별도로 사용하세요.</p>}
        {jobError && <p role="alert" className="model-error">작업 오류: {jobError}</p>}
        {desktop && <div role="status" className="compatibility-result">
          <strong>작업 상태: {job?.phase ?? (jobStatusLoaded ? "idle" : "확인 중")}</strong>
          <p>{job?.message ?? "대기 중"}</p>
          <p>경과 시간: {job?.elapsed_seconds ?? 0}초 / 최대 {job?.time_limit_seconds ?? 1800}초</p>
          {recoveryAdvice && <section className="generation-recovery" aria-label="오류 원인과 복구 안내">
            <strong>{recoveryAdvice.title}</strong>
            <p>{recoveryAdvice.explanation}</p>
            <p>{recoveryAdvice.nextStep}</p>
            {recoveryAdvice.offerSafePreset && <button type="button" className="refresh-button"
              onClick={applySafeTrial} disabled={jobBusy || jobLoading}>
              512×512 · 15스텝으로 변경 (자동 재실행 안 함)
            </button>}
            <p>GPU 또는 VRAM 환경을 다시 확인한 후 새 작업을 시작하려면 GPU 실행 동의를 다시 선택해야 합니다.</p>
          </section>}
          {job?.phase === "succeeded" && job.result && <div className="generation-metrics">
            <strong>결과 파일 디코딩·체크섬 확인</strong>
            <p>파일: {job.result.file_name} · 이미지 크기: {job.result.width}×{job.result.height}</p>
            <p>시드: {job.result.seed} · CLI 추론 및 모델 로딩 시간: {job.result.elapsed_seconds.toFixed(2)}초</p>
            <p>PyTorch 피크 할당 메모리: {job.result.measurement !== "torch_cuda_allocator" || job.result.peak_allocated_bytes == null ? "미측정" : (job.result.peak_allocated_bytes / 1073741824).toFixed(2) + " GiB"}</p>
            <p>PyTorch 피크 예약 메모리: {job.result.measurement !== "torch_cuda_allocator" || job.result.peak_reserved_bytes == null ? "미측정" : (job.result.peak_reserved_bytes / 1073741824).toFixed(2) + " GiB"}</p>
            <p>측정 상태: {job.result.measurement === "torch_cuda_allocator" ? "PyTorch CUDA 할당자 측정" : "GPU 할당자 측정 불가"}</p>
            <p className="generation-hash">PNG SHA-256: <code>{job.result.png_sha256}</code></p>
            <p>PNG 이미지 디코딩, 해상도 및 체크섬을 확인했습니다. GPU 전체 VRAM 사용량·그림 품질·프롬프트 준수는 검증하지 않았습니다.</p>
          </div>}
          <p>경과 시간은 실제 이미지 생성 진행률이 아닙니다. Windows Job Objects는 일반적인 하위 프로세스 종료를 요청하지만, 모든 외부 프로세스나 GPU 자원 회수를 보장하지 않습니다.</p>
        </div>}
        {checked && <div role="status" className={assessment.ok ? "compatibility-result" : "model-error"}>
          <strong>{assessment.summary}</strong>
          {assessment.warnings.map((notice, index) => <p key={index}>{notice}</p>)}
        </div>}
      </div>
    </section>
    <section className="generation-panel generation-gallery" aria-label="로컬 생성 결과">
      <div className="generation-heading"><h2>로컬 생성 결과</h2>
        <button type="button" className="refresh-button" onClick={() => setGalleryRefresh(x => x + 1)} disabled={!desktop || galleryLoading}>
          {galleryLoading ? "읽는 중..." : "이미지 새로고침"}
        </button>
      </div>
      <p className="muted">CLI 또는 Windows Tauri 개발판에서 생성된 PNG 중 최신 4개를 읽습니다. 이 갤러리는 실제 작업 진행률을 표시하지 않습니다.</p>
      {!desktop && <p className="empty-models">미리보기는 Tauri 데스크톱에서만 지원합니다.</p>}
      {galleryError && <p role="alert" className="model-error">결과 읽기 실패: {galleryError}</p>}
      {desktop && !galleryLoading && !galleryError && previews.length === 0 && <p className="empty-models">표시할 로컬 생성 이미지가 없습니다.</p>}
      {desktop && <div className="generation-preview-grid">
        {previews.map(x => <figure key={x.id}>
          <img src={x.image_src} alt={"로컬 생성 결과 " + x.id} loading="lazy" />
          <figcaption>{x.id} · {(x.size_bytes / 1024).toFixed(0)} KiB</figcaption>
        </figure>)}
      </div>}
      <div className="model-help"><strong>실제 이미지 생성 방법</strong>
        <p>Windows 개발판 실행기에 필요한 .venv 환경이 없으면 로컬 Python 터미널에서 <code>python backend/generate_sdxl.py --checkpoint "checkpoints/파일명.safetensors" --prompt "원하는 이미지" --execute</code> 명령을 사용합니다.</p>
        <p>CUDA PyTorch, Diffusers 및 로컬 SDXL 설정 파일이 필요합니다. CLI 생성이 성공하면 이 화면에서 새로고침하세요.</p>
      </div>
    </section>
  </div>;
}
