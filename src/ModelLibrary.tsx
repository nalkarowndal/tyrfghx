import { useEffect, useMemo, useState } from "react";
import { getCompatibility, type CompatibilityReport, type ModelRecord } from "./api";
import { isTauri } from "@tauri-apps/api/core";
import { importModelFromNativeDialog, type ImportCategory } from "./nativeModelImport";
import { compareNativeModels, verifyNativeModelHash, type ModelHashCheckStatus } from "./nativeModelCatalog";

const categories: Record<ModelRecord["category"], string> = {
  checkpoint: "체크포인트", lora: "LoRA", vae: "VAE",
};
const labels: Record<ModelRecord["validation"], string> = {
  metadata_only: "헤더 확인", invalid_header: "헤더 오류", blocked_legacy: "자동 로딩 차단",
};
const families: Record<NonNullable<ModelRecord["family"]>, string> = {
  sd15: "SD 1.x", sd2: "SD 2.x", sdxl: "SDXL", sd3: "SD3", flux: "FLUX",
};

export default function ModelLibrary({ items, isLoading, error, onRefresh }: {
  items: ModelRecord[]; isLoading: boolean; error: string; onRefresh: () => void;
}) {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<"all" | ModelRecord["category"]>("all");
  const [checkpointId, setCheckpointId] = useState("");
  const [loraId, setLoraId] = useState("");
  const [report, setReport] = useState<CompatibilityReport | null>(null);
  const [compareError, setCompareError] = useState("");
  const [comparing, setComparing] = useState(false);
  const [importCategory, setImportCategory] = useState<ImportCategory>("checkpoints");
  const [importBusy, setImportBusy] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [importError, setImportError] = useState("");
  const [hashBusy, setHashBusy] = useState<string | null>(null);
  const [hashResults, setHashResults] = useState<Record<string, ModelHashCheckStatus>>({});
  const [hashError, setHashError] = useState<string | null>(null);
  const desktopApp = isTauri();

  // A refreshed catalog must never display an old checksum match as current.
  useEffect(() => {
    setHashResults({});
    setHashError(null);
  }, [items]);

  async function recheckHash(modelId: string) {
    if (!desktopApp || hashBusy !== null) return;
    setHashBusy(modelId);
    setHashError(null);
    setHashResults(previous => {
      const next = { ...previous };
      delete next[modelId];
      return next;
    });
    try {
      const report = await verifyNativeModelHash(modelId);
      setHashResults(previous => ({ ...previous, [modelId]: report.status }));
    } catch {
      // Never render raw native filesystem errors or local paths in the UI.
      setHashError(modelId);
    } finally {
      setHashBusy(null);
    }
  }


  async function importModel() {
    if (importBusy || !desktopApp) return;
    setImportBusy(true);
    setImportMessage("");
    setImportError("");
    try {
      const result = await importModelFromNativeDialog(importCategory);
      if (result !== null) {
        setImportMessage(`모델 가져오기 완료: ${result.model_id}. 등록 당시 SHA-256: ${result.sha256}. Tauri 모델 목록을 새로고침합니다.`);
        onRefresh();
      } else {
        setImportMessage("파일 선택을 취소했습니다. 변경사항이 없습니다.");
      }
    } catch (reason) {
      setImportError(String(reason));
    } finally {
      setImportBusy(false);
    }
  }

  const visible = useMemo(() => items.filter(item => {
    const matchCategory = category === "all" || item.category === category;
    const matchText = [item.name, item.display_name, item.reported_architecture, item.family, item.notes]
      .some(part => part?.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
    return matchCategory && matchText;
  }), [items, category, search]);
  const checkpoints = items.filter(item => item.category === "checkpoint");
  const loras = items.filter(item => item.category === "lora");
  const readyToCheck = checkpoints.some(item => item.id === checkpointId)
    && loras.some(item => item.id === loraId);

  async function compare() {
    if (!readyToCheck || comparing) return;
    setComparing(true);
    setCompareError("");
    setReport(null);
    try {
      const result = desktopApp
        ? compareNativeModels(items, checkpointId, loraId)
        : await getCompatibility(checkpointId, loraId);
      setReport(result);
    } catch (reason) {
      setCompareError(String(reason));
    } finally {
      setComparing(false);
    }
  }

  return <section className="model-library" aria-label="로컬 모델 목록">
    <div className="model-heading">
      <div>
        <h2>로컬 모델 관리</h2>
        <p className="muted">모델 파일, 수동 등록 정보, 계열 일치 가능성을 확인합니다. 실제 생성 여부는 검증하지 않습니다.</p>
      </div>
      <button type="button" className="refresh-button" onClick={() => { setReport(null); setHashResults({}); setHashError(null); onRefresh(); }} disabled={isLoading || hashBusy !== null}>
        {isLoading ? "검색 중..." : "목록 새로고침"}
      </button>
    </div>
    <section className="model-help" aria-label="데스크톱 모델 파일 가져오기">
      <strong>데스크톱 모델 가져오기 (M2-4)</strong>
      <p>Tauri 창에서 모델 종류를 선택하고 파일을 지정하면 원본을 변경하지 않고 aiimage 모델 폴더에 안전하게 복사합니다.</p>
      <div className="compatibility-form">
        <label>가져올 모델 종류
          <select aria-label="가져올 모델 종류" value={importCategory} disabled={importBusy} onChange={e => setImportCategory(e.target.value as ImportCategory)}>
            <option value="checkpoints">체크포인트</option>
            <option value="loras">LoRA</option>
            <option value="vae">VAE</option>
          </select>
        </label>
        <button className="refresh-button" type="button" onClick={importModel} disabled={!desktopApp || importBusy}>
          {importBusy ? "가져오는 중..." : "파일 선택 후 가져오기"}
        </button>
      </div>
      {!desktopApp && <p className="muted">브라우저에서는 파일 가져오기 버튼을 사용할 수 없습니다. Tauri 데스크톱 앱에서 실행하세요.</p>}
      {importMessage && <p role="status" className="compatibility-result">{importMessage}</p>}
      {importError && <p role="alert" className="model-error">파일 가져오기 실패: {importError}</p>}
      <p className="muted">개발 중에는 기존 models 폴더를 사용합니다. 배포판은 앱 전용 데이터 폴더를 사용하며, Tauri의 모델 목록과 계열 비교는 Python 없이 동작합니다. 이미지 생성용 Python 백엔드 자동 실행은 아직 구현되지 않았습니다.</p>
    </section>
    <div className="model-help">
      <strong>모델 추가 및 정보 등록</strong>
      <p>Windows에서 파일 선택 창으로 등록하려면 <code>backend</code> 폴더에서 <code>python model_import.py --category checkpoints</code> 명령을 실행하세요. LoRA는 <code>--category loras</code>, VAE는 <code>--category vae</code>로 설정합니다.</p>
      <p>이미 파일을 수동으로 넣었다면 <code>models/checkpoints</code>, <code>models/loras</code>, <code>models/vae</code> 폴더를 확인한 뒤 새로고침하세요.</p>
      <p>모델 계열을 알고 있다면 로컬 CLI에서 <code>python model_register.py loras/style.safetensors --family sdxl</code> 명령으로 정보를 등록할 수 있습니다 (backend 폴더에서 실행).</p>
      <p>무결성 검증은 백엔드 폴더에서 <code>python model_import.py --category checkpoints --verify "checkpoints/파일명.safetensors"</code> 명령을 실행하세요. 등록 시 저장된 해시와 실제 파일을 재비교합니다.</p>
      <p>브라우저에서는 CLI만, Tauri 창에서는 위 파일 선택 버튼으로 가져올 수 있습니다. 모델 호환성은 보장하지 않습니다.</p>
    </div>
    {error && <p role="alert" className="model-error">모델 목록 오류: {error}</p>}
    <div className="model-filters">
      <label>이름 검색
        <input aria-label="모델 이름 검색" placeholder="파일명, 모델명, 계열" value={search} onChange={e => setSearch(e.target.value)} />
      </label>
      <label>종류
        <select aria-label="모델 종류" value={category} onChange={e => setCategory(e.target.value as typeof category)}>
          <option value="all">전체</option>
          <option value="checkpoint">체크포인트</option>
          <option value="lora">LoRA</option>
          <option value="vae">VAE</option>
        </select>
      </label>
    </div>
    {isLoading ? <p className="muted" role="status">로컬 모델 파일을 확인하는 중입니다.</p>
      : !error && visible.length === 0 ? <p className="empty-models">표시할 모델이 없습니다. 검색 조건 또는 파일 위치를 확인해 주세요.</p>
      : <div className="model-list">{visible.map(model => <article className="model-item" key={model.id}>
        <div className="model-title">
          <strong title={model.name}>{model.display_name || model.name}</strong>
          <span>{categories[model.category]}</span>
        </div>
        {model.display_name && <p className="muted">파일명: {model.name}</p>}
        <div className="model-details">
          <span>{model.file_format}</span>
          <span>{(model.size_bytes / (1024 * 1024)).toFixed(1)} MiB</span>
          <span>{labels[model.validation]}</span>
          <span>{model.family ? families[model.family] : "계열 미확인"}</span>
        </div>
        {model.family && <p className="muted">계열 정보 출처: {model.family_source === "manual" ? "사용자 수동 지정" : "모델 파일 헤더(미검증)"}</p>}
        {model.reported_architecture && <p className="muted">헤더 아키텍처: {model.reported_architecture}</p>}
        <p className="muted">
          무결성 기록: {model.integrity_state === "snapshot_unchanged"
            ? "가져올 당시 크기·수정 시각 유지 (현재 SHA-256 재검사 아님)"
            : model.integrity_state === "file_changed"
              ? "파일 크기·수정 시각 변경 감지 — SHA-256 재검증 필요"
              : "SHA-256 기록 없음 (수동 파일일 수 있음)"}
        </p>
        {model.recorded_sha256 && <p className="muted" title={model.recorded_sha256}>
          등록 시 SHA-256: <code>{model.recorded_sha256}</code>
        </p>}
        {desktopApp && model.file_format === "safetensors" && <div className="model-hash-check">
          <button type="button" className="refresh-button"
            disabled={hashBusy !== null || isLoading}
            onClick={() => recheckHash(model.id)}
            aria-label={`SHA-256 현재 파일 재검증: ${model.name}`}>
            {hashBusy === model.id ? "SHA-256 검사 중..." : "현재 파일 SHA-256 검증"}
          </button>
          {hashResults[model.id] && <p role="status" className={hashResults[model.id] === "mismatch" ? "model-error" : "muted"}>
            {hashResults[model.id] === "match"
              ? "등록 당시 기록과 현재 SHA-256이 일치합니다 (검사 시점 기준)."
              : hashResults[model.id] === "mismatch"
                ? "주의: 기록된 SHA-256과 현재 파일이 다릅니다. 해당 모델을 사용하지 마세요."
                : "등록된 SHA-256이 없습니다. 원본 출처와 체크섬을 별도로 확인하세요."}
          </p>}
          {hashError === model.id && <p role="alert" className="model-error">
            SHA-256 검사에 실패했습니다. 파일 또는 무결성 기록을 확인하세요.
          </p>}
        </div>}
        {model.potential_duplicate_ids.length > 0 && <p className="muted">
          중복 가능 파일: {model.potential_duplicate_ids.join(", ")} (등록 당시 기록 기준)
        </p>}
        {model.license && <p className="muted">라이선스 (사용자 기록): {model.license}</p>}
        {model.notes && <p className="muted">메모: {model.notes}</p>}
        <p className="muted">{model.note}</p>
      </article>)}</div>}
    <section className="compatibility" aria-label="LoRA 사전 호환성 확인">
      <h3>체크포인트 + LoRA 계열 비교</h3>
      <p className="muted">SAI ModelSpec 및 수동 정보에 기반한 참고용 검사입니다. 동일 계열이어도 실제로 작동한다는 보장은 없습니다.</p>
      <div className="compatibility-form">
        <label>체크포인트
          <select value={checkpointId} onChange={e => { setCheckpointId(e.target.value); setReport(null); }}>
            <option value="">선택하세요</option>
            {checkpoints.map(item => <option value={item.id} key={item.id}>{item.display_name || item.name}</option>)}
          </select>
        </label>
        <label>LoRA
          <select value={loraId} onChange={e => { setLoraId(e.target.value); setReport(null); }}>
            <option value="">선택하세요</option>
            {loras.map(item => <option value={item.id} key={item.id}>{item.display_name || item.name}</option>)}
          </select>
        </label>
        <button type="button" className="refresh-button" disabled={!readyToCheck || isLoading || comparing} onClick={compare}>
          {comparing ? "확인 중..." : "계열 일치 여부 확인"}
        </button>
      </div>
      {compareError && <p role="alert" className="model-error">비교 오류: {compareError}</p>}
      {report && <p role="status" className="compatibility-result">
        <strong>{report.status === "possible_match" ? "동일 계열 가능성" : report.status === "family_mismatch" ? "계열 불일치" : "확인 필요"}</strong>
        {" — "}{report.summary}
      </p>}
    </section>
  </section>;
}
