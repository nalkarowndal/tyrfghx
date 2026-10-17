import { useEffect, useState } from "react";
import { getStatus, type StudioStatus } from "./api";
const tools = ["이미지 생성", "이미지 편집", "영상 생성", "워크플로", "모델 관리"];
export default function App() {
  const [status, setStatus] = useState<StudioStatus | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(tools[0]);
  useEffect(() => {
    const controller = new AbortController();
    getStatus(controller.signal).then(setStatus).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);
  return <div className="shell"><aside className="sidebar"><h1>aiimage</h1><p className="muted">Local Creative Studio</p><nav aria-label="작업 도구">{tools.map(t => <button key={t} className={active === t ? "selected" : ""} onClick={() => setActive(t)}>{t}</button>)}</nav></aside><main><header><strong>{active}</strong><span className="state">{status ? "백엔드 연결됨" : error ? "백엔드 연결 안 됨" : "연결 확인 중"}</span></header><section className="workspace"><div className="placeholder"><div className="symbol">◇</div><h2>{active} 작업 공간</h2><p>첫 번째 기반 구축 단계입니다. 아직 GPU 생성 엔진과 모델이 연결되지 않았습니다.</p><button disabled aria-label="아직 지원하지 않는 생성 기능">생성 시작 (준비 중)</button></div></section></main><aside className="inspector"><h2>작업 상태</h2><p>단계: M1 기반 구축</p><h3>실행 엔진</h3>{status?.engines.map(e => <div className="engine" key={e.name}><b>{e.name}</b><span>{e.status === "ready" ? "사용 가능" : "미연결"}</span><small>{e.note}</small></div>)}{!status && <p className="muted">{error || "상태를 불러오는 중..."}</p>}<h3>안내</h3><p className="muted">이 화면은 실제 생성 기능을 시뮬레이션하지 않습니다. 엔진 연결 전에는 생성 버튼을 사용할 수 없습니다.</p></aside></div>;
}
