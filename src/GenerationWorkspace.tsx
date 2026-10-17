import { useEffect, useMemo, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import type { ModelRecord } from "./api";
import { DEFAULT_IMAGE_SETTINGS, preflightImageSettings, type ImageSettings } from "./generationWorkspacePlan";
import { getNativeGenerationPreviews, type GenerationPreview } from "./nativeGenerationGallery";

export default function GenerationWorkspace({ models, loadingModels, modelsError, onRefreshModels }: {
  models: ModelRecord[]; loadingModels: boolean; modelsError: string; onRefreshModels: () => void;
}) {
  const [settings, setSettings] = useState<ImageSettings>(DEFAULT_IMAGE_SETTINGS);
  const [checked, setChecked] = useState(false);
  const [previews, setPreviews] = useState<GenerationPreview[]>([]);
  const [galleryLoading, setGalleryLoading] = useState(false);
  const [galleryError, setGalleryError] = useState("");
  const [galleryRefresh, setGalleryRefresh] = useState(0);
  const desktop = isTauri();
  const eligibleModels = useMemo(() => models.filter(x => x.category === "checkpoint"), [models]);
  const assessment = preflightImageSettings(settings, models);
  const update = (field: keyof ImageSettings, value: string | number) => {
    setSettings(previous => ({ ...previous, [field]: value }));
    setChecked(false);
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

  return <div className="generation-layout">
    <section className="generation-panel" aria-label="이미지 생성 설정">
      <div className="generation-heading"><h2>이미지 생성</h2><span className="generation-tag">M3-2 · 준비 화면</span></div>
      <p className="muted">로컬 SDXL 이미지 생성 설정과 결과 확인을 위한 화면입니다. GPU 실행은 아직 CLI에서만 가능합니다.</p>
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
        <div className="generation-actions">
          <button type="button" className="refresh-button" onClick={() => setChecked(true)}>입력 사전 검사</button>
          <button type="button" disabled title="실제 GPU 생성은 별도 CLI에서만 지원합니다.">이미지 생성 (미연결)</button>
        </div>
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
      <p className="muted">사용자가 M3-1 CLI에서 직접 생성한 PNG 중 최신 4개만 표시합니다. 자동 생성·모델 로딩 기능은 없습니다.</p>
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
        <p>현재는 로컬 Python 터미널에서 <code>python backend/generate_sdxl.py --checkpoint "checkpoints/파일명.safetensors" --prompt "원하는 이미지" --execute</code> 명령을 사용합니다.</p>
        <p>CUDA PyTorch, Diffusers 및 로컬 SDXL 설정 파일이 필요합니다. CLI 생성이 성공하면 이 화면에서 새로고침하세요.</p>
      </div>
    </section>
  </div>;
}
