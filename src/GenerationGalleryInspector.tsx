import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { GenerationPreview } from "./nativeGenerationGallery";
import { adjacentPreviewId, adjustImageZoom, imageDimensionLabel, selectPreview, type ImageZoom } from "./generationGalleryView";

/** Review only native-validated fixed-root PNG previews. No file paths or GPU IPC. */
export default function GenerationGalleryInspector({ previews }: { previews: GenerationPreview[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState<ImageZoom>(100);
  const detailsRef = useRef<HTMLElement>(null);
  const selected = selectPreview(previews, selectedId);
  const previous = selected ? adjacentPreviewId(previews, selected.id, -1) : null;
  const next = selected ? adjacentPreviewId(previews, selected.id, 1) : null;

  useEffect(() => {
    if (selectedId && !selectPreview(previews, selectedId)) setSelectedId(null);
  }, [previews, selectedId]);

  useEffect(() => {
    if (selected) detailsRef.current?.focus();
  }, [selected?.id]);

  function openImage(id: string) {
    if (!selectPreview(previews, id)) return;
    setSelectedId(id);
    setZoom(100);
  }

  function navigate(id: string | null) {
    if (id && selectPreview(previews, id)) {
      setSelectedId(id);
      setZoom(100);
    }
  }

  function handleKeys(e: KeyboardEvent<HTMLElement>) {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (e.key === "Escape") {
      e.preventDefault();
      setSelectedId(null);
    } else if (e.key === "ArrowLeft" && previous) {
      e.preventDefault();
      navigate(previous);
    } else if (e.key === "ArrowRight" && next) {
      e.preventDefault();
      navigate(next);
    }
  }

  return <>
    <div className="generation-preview-grid">
      {previews.map(item => <figure key={item.id}>
        <button type="button" className="gallery-preview-action"
          onClick={() => openImage(item.id)} aria-label={`이미지 자세히 보기: ${item.id}`}>
          <img src={item.image_src} alt={`로컬 생성 이미지 ${item.id}`} loading="lazy" />
          <span className="gallery-preview-open">확대해서 보기</span>
        </button>
        <figcaption>{item.id} · {imageDimensionLabel(item)} · {(item.size_bytes / 1024).toFixed(0)} KiB</figcaption>
      </figure>)}
    </div>
    {selected && <section className="gallery-inspector" role="region"
      aria-label="선택한 이미지 상세 보기" tabIndex={-1} ref={detailsRef} onKeyDown={handleKeys}>
      <div className="gallery-inspector-heading">
        <h3>이미지 상세 보기</h3>
        <button type="button" onClick={() => setSelectedId(null)} className="refresh-button">닫기 (Esc)</button>
      </div>
      <p className="muted">확대 시 원본의 저장된 픽셀을 브라우저에 표시합니다. PNG 무결성 검사는 수행됐지만 시각적 품질은 별도 판단이 필요합니다.</p>
      <div className="gallery-inspector-controls">
        <button type="button" onClick={() => navigate(previous)} disabled={!previous} aria-label="이전 이미지">← 이전</button>
        <button type="button" onClick={() => setZoom(v => adjustImageZoom(v, -1))}
          disabled={zoom === 50} aria-label="이미지 축소">−</button>
        <span aria-live="polite">화면 표시 배율 {zoom}%</span>
        <button type="button" onClick={() => setZoom(v => adjustImageZoom(v, 1))}
          disabled={zoom === 200} aria-label="이미지 확대">+</button>
        <button type="button" onClick={() => { setZoom(100); }} disabled={zoom === 100}>100%</button>
        <button type="button" onClick={() => navigate(next)} disabled={!next} aria-label="다음 이미지">다음 →</button>
      </div>
      <div className="gallery-inspector-scroll" aria-label="이미지 확대 미리보기">
        <img src={selected.image_src} alt={`확대 미리보기 ${selected.id}`}
          draggable={false}
          style={{ width: selected.width * zoom / 100, height: "auto", maxWidth: "none" }} />
      </div>
      <p className="gallery-inspector-meta">{selected.id} · 실제 이미지 {imageDimensionLabel(selected)} · {(selected.size_bytes / 1024).toFixed(0)} KiB</p>
      <p className="muted">이 영역에 포커스한 상태에서는 좌우 방향키로 이미지 이동, Esc로 닫기가 가능합니다. 외부 파일을 열거나 GPU 작업을 다시 시작하지 않습니다.</p>
    </section>}
  </>;
}
