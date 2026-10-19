import { useEffect, useMemo, useState } from "react";
import { getStatus, getModels, type ModelRecord, type StudioStatus } from "./api";
import ModelLibrary from "./ModelLibrary";
import GenerationWorkspace from "./GenerationWorkspace";
import { isTauri } from "@tauri-apps/api/core";
import { getNativeModels } from "./nativeModelCatalog";
import { loadModelCatalog } from "./modelCatalogRecovery";
import { bundledBackendEnabled, restartBackend } from "./nativeBackend";
import { createBackendStatusLoader } from "./backendStatus";

const tools = ["이미지 생성", "이미지 편집", "영상 생성", "워크플로", "모델 관리"];

export default function App() {
  const [status, setStatus] = useState<StudioStatus | null>(null);
  const [error, setError] = useState("");
  const [managedBackend, setManagedBackend] = useState(false);
  const [restartingBackend, setRestartingBackend] = useState(false);
  const [active, setActive] = useState(tools[0]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [modelsError, setModelsError] = useState("");
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const desktopApp = isTauri();
  const backendLoader = useMemo(() => createBackendStatusLoader(
    next => setStatus(previous => JSON.stringify(previous) === JSON.stringify(next) ? previous : next),
    setError, setRestartingBackend,
  ), []);

  useEffect(() => {
    const controller = new AbortController();
    void bundledBackendEnabled().then(enabled => {
      if (!controller.signal.aborted) setManagedBackend(enabled);
    }).catch(() => {});
    const refresh = () => backendLoader.run(() => getStatus(controller.signal));
    void refresh();
    const timer = setInterval(() => { void refresh(); }, 15000);
    return () => { controller.abort(); clearInterval(timer); backendLoader.cancel(); };
  }, [backendLoader]);

  async function retryBackend() {
    if (restartingBackend) return;
    await backendLoader.run(restartBackend, true);
  }
  useEffect(() => {
    if (!["모델 관리", "이미지 생성"].includes(active)) return;
    const controller = new AbortController();
    void loadModelCatalog(
      () => desktopApp ? getNativeModels() : getModels(controller.signal),
      {
        isCurrent: () => !controller.signal.aborted,
        onStart: () => {
          // Never retain a usable checkpoint while the new snapshot is unknown.
          setModels([]);
          setModelsError("");
          setModelsLoaded(false);
          setLoadingModels(true);
        },
        onLoaded: items => { setModels(items); setModelsLoaded(true); },
        onFailed: safeMessage => {
          setModelsLoaded(false);
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
    setModelsLoaded(false);
    setModels([]);
    setModelsError("");
    setLoadingModels(true);
    setRefreshKey(value => value + 1);
  }

  function selectTool(tool: string) {
    if (tool !== active && (tool === "모델 관리" || tool === "이미지 생성")) {
      setModelsLoaded(false);
      setModels([]);
      setModelsError("");
      // Retrying a browser catalog request is allowed even if /api/status previously failed.
      setLoadingModels(true);
    }
    setActive(tool);
  }

  const availableModels = loadingModels || modelsError ? [] : models;

  return <div className="shell">
    <aside className="sidebar"><h1>aiimage</h1><p className="muted">Local Creative Studio</p>
      <nav aria-label="작업 도구">{tools.map(t => <button type="button" key={t} className={active === t ? "selected" : ""} aria-current={active === t ? "page" : undefined} onClick={() => selectTool(t)}>{t}</button>)}</nav>
    </aside>
    <main><header><strong>{active}</strong><span className="state">{status ? "Python API 연결됨" : desktopApp ? "Tauri 모델 관리 사용 가능 · Python API 미연결" : modelsLoaded ? "모델 API 연결됨 · 상태 API 확인 필요" : error ? "백엔드 연결 안 됨" : "연결 확인 중"}</span></header>
      {active === "이미지 생성"
        ? <section className="workspace model-workspace"><GenerationWorkspace models={availableModels} loadingModels={loadingModels} modelsError={modelsError} onRefreshModels={requestCatalogRefresh} /></section>
        : active === "모델 관리"
        ? <div className="workspace model-workspace"><ModelLibrary items={availableModels} isLoading={loadingModels} error={modelsError} onRefresh={requestCatalogRefresh} /></div>
        : <section className="workspace"><div className="placeholder"><div className="symbol">◇</div><h2>{active} 작업 공간</h2><p>현재 생성 엔진은 연결되지 않았습니다. 모델 목록 등록은 ‘모델 관리’ 메뉴에서 시작할 수 있습니다.</p><button type="button" disabled>생성 시작 (준비 중)</button></div></section>}
    </main>
    <aside className="inspector"><h2>작업 상태</h2><p>M3-2 · 생성 설정 및 결과 갤러리</p>
      <h3>실행 엔진</h3>{status?.engines.map(e => <div className="engine" key={e.name}><b>{e.name}</b><span>{e.status === "ready" ? "사용 가능" : "미연결"}</span><small>{e.note}</small></div>)}
      {status?.runtime_preflight && <section aria-label="AI 런타임 사전 진단">
        <h3>AI 런타임 사전 진단</h3>
        <p className="muted">설치된 패키지 정보만 확인했습니다. GPU·CUDA 동작, 모델 로딩 및 실제 이미지 생성은 검증하지 않았습니다.</p>
        <ul>{status.runtime_preflight.packages.map(item =>
          <li key={item.package}>{item.package}: {item.state === "detected" ? `설치 정보 확인 (${item.version})` : item.state === "missing" ? "미설치" : "확인 불가"}</li>
        )}</ul>
        <p className="muted">생성 엔진 상태: 미검증 · 자동 다운로드 또는 GPU 실행 없음</p>
        {status.runtime_preflight.setup_plan && <section aria-label="AI 추론 환경 준비 계획">
          <h3>독립 AI 추론 환경 준비</h3>
          <p className="muted">위의 설치 정보는 현재 읽기 전용 Python API 프로세스 기준입니다. 별도 추론 환경은 아직 앱에 연결되지 않았습니다.</p>
          <p className="muted">권장 구조: Python 3.12 전용 가상환경 · 별도 프로세스 · 사용자가 선택하고 승인한 설치</p>
          <p className="muted">PyTorch 패키지 표기: {status.runtime_preflight.setup_plan.torch_wheel_hint.kind === "cuda_wheel_metadata"
            ? `CUDA 휠 태그 ${status.runtime_preflight.setup_plan.torch_wheel_hint.tag} (GPU 호환성 미검증)`
            : status.runtime_preflight.setup_plan.torch_wheel_hint.kind === "cpu_wheel_metadata"
            ? "CPU 휠 표기 (GPU 호환성 미검증)"
            : "확인 불가 (GPU 호환성 미검증)"}</p>
          <p className="muted">자동 설치·다운로드·GPU 테스트·모델 실행: 비활성. 실제 추론 실행 전 별도 동의가 필요합니다.</p>
          <p className="muted">설치 검토: pytorch.org/get-started/locally/ · docs.python.org/3/library/venv.html</p>
        </section>}

      </section>}
      {!status && <p className="muted">{error || "백엔드 상태 확인 중..."}</p>}
      {managedBackend && error && <button type="button" disabled={restartingBackend} onClick={() => { void retryBackend(); }}>백엔드 다시 시작</button>}
      <h3>모델 목록</h3><p className="muted">찾은 모델: {availableModels.length}개</p>
      <h3>안내</h3><p className="muted">헤더 검사 결과가 정상이어도 실제 생성에 사용할 수 있다는 의미는 아닙니다. M3-1 추론 CLI는 별도로 사용하며, 이 UI에서 GPU 생성 시작은 아직 지원하지 않습니다.</p>
    </aside>
  </div>;
}
