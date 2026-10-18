import { useEffect, useState } from "react";
import { getStatus, getModels, type ModelRecord, type StudioStatus } from "./api";
import ModelLibrary from "./ModelLibrary";
import GenerationWorkspace from "./GenerationWorkspace";
import { isTauri } from "@tauri-apps/api/core";
import { getNativeModels } from "./nativeModelCatalog";
import { loadModelCatalog } from "./modelCatalogRecovery";

const tools = ["이미지 생성", "이미지 편집", "영상 생성", "워크플로", "모델 관리"];

export default function App() {
  const [status, setStatus] = useState<StudioStatus | null>(null);
  const [error, setError] = useState("");
  const [active, setActive] = useState(tools[0]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [modelsError, setModelsError] = useState("");
  const [loadingModels, setLoadingModels] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const desktopApp = isTauri();

  useEffect(() => {
    const controller = new AbortController();
    getStatus(controller.signal).then(setStatus).catch(e => { if (!controller.signal.aborted) setError(String(e)); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!["모델 관리", "이미지 생성"].includes(active) || (!status && !desktopApp)) return;
    const controller = new AbortController();
    void loadModelCatalog(
      () => desktopApp ? getNativeModels() : getModels(controller.signal),
      {
        isCurrent: () => !controller.signal.aborted,
        onStart: () => {
          // Never retain a usable checkpoint while the new snapshot is unknown.
          setModels([]);
          setModelsError("");
          setLoadingModels(true);
        },
        onLoaded: items => setModels(items),
        onFailed: safeMessage => {
          setModels([]);
          setModelsError(safeMessage);
        },
        onFinished: () => setLoadingModels(false),
      },
    );
    return () => controller.abort();
  }, [active, status, refreshKey, desktopApp]);

  function requestCatalogRefresh() {
    // Clear synchronously on click, not only later when the effect runs.
    setModels([]);
    setModelsError("");
    setLoadingModels(true);
    setRefreshKey(value => value + 1);
  }

  function selectTool(tool: string) {
    if (tool !== active && (tool === "모델 관리" || tool === "이미지 생성")) {
      setModels([]);
      setModelsError("");
      // A Python-less browser cannot request models until its API connects.
      setLoadingModels(desktopApp || status !== null);
    }
    setActive(tool);
  }

  const availableModels = loadingModels || modelsError ? [] : models;

  return <div className="shell">
    <aside className="sidebar"><h1>aiimage</h1><p className="muted">Local Creative Studio</p>
      <nav aria-label="작업 도구">{tools.map(t => <button type="button" key={t} className={active === t ? "selected" : ""} aria-current={active === t ? "page" : undefined} onClick={() => selectTool(t)}>{t}</button>)}</nav>
    </aside>
    <main><header><strong>{active}</strong><span className="state">{status ? "Python API 연결됨" : desktopApp ? "Tauri 모델 관리 사용 가능 · Python API 미연결" : error ? "백엔드 연결 안 됨" : "연결 확인 중"}</span></header>
      {active === "이미지 생성"
        ? <section className="workspace model-workspace"><GenerationWorkspace models={availableModels} loadingModels={loadingModels} modelsError={desktopApp || status ? modelsError : error || "모델 목록을 보려면 Python API를 실행하세요."} onRefreshModels={requestCatalogRefresh} /></section>
        : active === "모델 관리"
        ? <div className="workspace model-workspace"><ModelLibrary items={availableModels} isLoading={loadingModels} error={desktopApp || status ? modelsError : error || "백엔드를 실행해야 모델 목록을 확인할 수 있습니다."} onRefresh={requestCatalogRefresh} /></div>
        : <section className="workspace"><div className="placeholder"><div className="symbol">◇</div><h2>{active} 작업 공간</h2><p>현재 생성 엔진은 연결되지 않았습니다. 모델 목록 등록은 ‘모델 관리’ 메뉴에서 시작할 수 있습니다.</p><button type="button" disabled>생성 시작 (준비 중)</button></div></section>}
    </main>
    <aside className="inspector"><h2>작업 상태</h2><p>M3-2 · 생성 설정 및 결과 갤러리</p>
      <h3>실행 엔진</h3>{status?.engines.map(e => <div className="engine" key={e.name}><b>{e.name}</b><span>{e.status === "ready" ? "사용 가능" : "미연결"}</span><small>{e.note}</small></div>)}
      {!status && <p className="muted">{error || "백엔드 상태 확인 중..."}</p>}
      <h3>모델 목록</h3><p className="muted">찾은 모델: {desktopApp || status ? availableModels.length : "연결 필요"}개</p>
      <h3>안내</h3><p className="muted">헤더 검사 결과가 정상이어도 실제 생성에 사용할 수 있다는 의미는 아닙니다. M3-1 추론 CLI는 별도로 사용하며, 이 UI에서 GPU 생성 시작은 아직 지원하지 않습니다.</p>
    </aside>
  </div>;
}
