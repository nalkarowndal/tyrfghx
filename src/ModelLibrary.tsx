import { useMemo, useState } from "react";
import { getCompatibility, type CompatibilityReport, type ModelRecord } from "./api";

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
      const result = await getCompatibility(checkpointId, loraId);
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
      <button type="button" className="refresh-button" onClick={() => { setReport(null); onRefresh(); }} disabled={isLoading}>
        {isLoading ? "검색 중..." : "목록 새로고침"}
      </button>
    </div>
    <div className="model-help">
      <strong>모델 추가 및 정보 등록</strong>
      <p>파일을 <code>models/checkpoints</code>, <code>models/loras</code>, <code>models/vae</code>에 넣고 새로고침하세요.</p>
      <p>모델 계열을 알고 있다면 로컬 CLI에서 <code>python model_register.py loras/style.safetensors --family sdxl</code> 명령으로 정보를 등록할 수 있습니다 (backend 폴더에서 실행).</p>
      <p>수동 설정은 모델 실행 가능 여부를 증명하지 않으며, 네트워크로 파일을 전송하지 않습니다.</p>
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
