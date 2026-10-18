/**
 * M3-26 opt-in REAL Windows Tauri release-UI smoke via tauri-driver WebDriver.
 * No downloaded models, model imports, GPU consent, screenshots or raw DOM logs.
 * A release binary deliberately disables GPU jobs. Run ONLY with --run.
 *
 * Official reference: https://v2.tauri.app/develop/tests/webdriver/
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer } from "node:net";

// A dedicated pair of ephemeral loopback ports prevents accidental connections
// to another user's / previous test's WebDriver on ports 4444/4445.
async function ephemeralLoopbackPort() {
  const server = createServer();
  try {
    await new Promise((ok, fail) => {
      server.once("error", fail);
      server.listen(0, "127.0.0.1", ok);
    });
    const address = server.address();
    if (!address || typeof address === "string" || address.port < 1) {
      throw new Error("Failed to reserve an ephemeral test port.");
    }
    return address.port;
  } finally {
    if (server.listening) await new Promise(done => server.close(done));
  }
}
export async function allocateDriverPorts() {
  const port = await ephemeralLoopbackPort();
  let nativePort = await ephemeralLoopbackPort();
  // The native driver and intermediary require distinct ports.
  for (let attempt = 0; nativePort === port && attempt < 5; attempt++) {
    nativePort = await ephemeralLoopbackPort();
  }
  if (port === nativePort) throw new Error("Unable to isolate both driver ports.");
  return { port, nativePort, url: `http://127.0.0.1:${port}` };
}
const ELEM = "element-6066-11e4-a52e-4f735466cecf";
const sleep = ms => new Promise(done => setTimeout(done, ms));

export async function requestWebDriver(base, method, route, body, timeoutMillis = 12_000) {
  // Report only a safe request category; never print a path, session ID,
  // browser stack, private prompt, returned DOM or full WebDriver payload.
  const category = route === "/status" ? "status"
    : route === "/session" ? "session"
    : route.startsWith("/session/") ? "command" : "other";
  let response;
  try {
    response = await fetch(base + route, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMillis),
    });
  } catch (error) {
    const timedOut = error?.name === "TimeoutError" || error?.name === "AbortError";
    throw new Error(timedOut
      ? `WebDriver ${category} request timed out after ${timeoutMillis}ms`
      : `WebDriver ${category} connection failed`);
  }
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`WebDriver ${category} returned malformed JSON`);
  }
  if (!response.ok || payload?.value?.error) {
    const code = typeof payload?.value?.error === "string"
      ? payload.value.error.slice(0, 64) : "protocol_error";
    throw new Error(`WebDriver ${category} rejected request: ${code}`);
  }
  return payload.value;
}

export async function waitForDriver(base, maxMillis = 30_000, driverFailed = () => false) {
  const deadline = Date.now() + maxMillis;
  while (Date.now() < deadline) {
    if (driverFailed()) throw new Error("Local Tauri WebDriver process exited before readiness.");
    try {
      const status = await requestWebDriver(base, "GET", "/status", undefined, 4_000);
      if (status?.ready !== false) return;
    } catch { /* expected before driver binds its local socket */ }
    await sleep(400);
  }
  throw new Error("Local WebDriver did not become ready.");
}

export async function runWindowsUiSmoke(base, application) {
  // Launching a native Windows WebView2 process often exceeds a typical
  // fast DOM-command timeout; keep startup bounded but distinct from it.
  const session = await requestWebDriver(base, "POST", "/session", {
    capabilities: { alwaysMatch: { browserName: "wry", "tauri:options": { application } } },
  }, 90_000);
  const sid = session?.sessionId;
  assert.match(sid ?? "", /^[a-zA-Z0-9-]{8,128}$/, "No valid native GUI session");
  const route = path => `/session/${sid}${path}`;
  const call = (method, path, payload) => requestWebDriver(base, method, route(path), payload);
  const elements = async css => {
    const result = await call("POST", "/elements", { using: "css selector", value: css });
    return result.map(item => item[ELEM] ?? item.ELEMENT).filter(Boolean);
  };
  const getText = id => call("GET", `/element/${id}/text`);
  const click = id => call("POST", `/element/${id}/click`, {});
  const selected = id => call("GET", `/element/${id}/selected`);
  const bodyText = async () => {
    const [body] = await elements("body");
    if (!body) throw new Error("Native UI body is absent");
    return getText(body);
  };
  const waitText = async expected => {
    const limit = Date.now() + 12_000;
    while (Date.now() < limit) {
      if ((await bodyText()).includes(expected)) return;
      await sleep(200);
    }
    throw new Error(`Expected safe UI marker absent: ${expected}`);
  };
  // A disabled button alone does not prove the release binary blocks GPU:
  // missing model or consent disables that button even on unsafe debug builds.
  // Require a successful response from the actual Tauri IPC policy command.
  const awaitNativeReleasePolicy = async () => {
    const until = Date.now() + 12_000;
    while (Date.now() < until) {
      const text = await bodyText();
      if (text.includes("로컬 GPU 실행 정책 확인됨: 배포판 비활성")) return;
      if (text.includes("로컬 GPU 실행 정책 확인됨: 개발판 실행 가능")) {
        throw new Error("Unexpected native GPU runner availability in release E2E");
      }
      if (text.includes("로컬 GPU 실행 정책 확인 실패")) {
        throw new Error("Native GPU availability IPC failed; release policy not attested");
      }
      await sleep(200);
    }
    throw new Error("Native release GPU policy was never attested via IPC");
  };
  const clickButton = async (selector, text) => {
    const deadline = Date.now() + 12_000;
    while (Date.now() < deadline) {
      const ids = await elements(selector);
      for (const id of ids) {
        if ((await getText(id)).trim() === text) {
          const enabled = await call("GET", `/element/${id}/enabled`);
          if (enabled) {
            await click(id);
            return;
          }
        }
      }
      await sleep(200);
    }
    throw new Error(`Expected enabled UI control absent: ${text}`);
  };

  try {
    await waitText("aiimage");
    await clickButton('nav[aria-label="작업 도구"] button', "모델 관리");
    await waitText("로컬 모델 관리");
    await waitText("데스크톱 모델 가져오기");
    await clickButton("button", "목록 새로고침");

    // Exercise catalog failure recovery if a safe error appears naturally.
    // Never simulate failure by editing real model folders or touching weights.
    const catalogState = async () => {
      const text = await bodyText();
      if (text.includes("모델 목록 오류:")) return "error";
      if (text.includes("표시할 모델이 없습니다.") || (await elements(".model-item")).length > 0) {
        return "loaded";
      }
      return "pending";
    };
    const awaitCatalog = async () => {
      const limit = Date.now() + 12_000;
      while (Date.now() < limit) {
        const state = await catalogState();
        if (state !== "pending") return state;
        await sleep(200);
      }
      throw new Error("Catalog never reached a loaded or safe failure state.");
    };
    const firstCatalog = await awaitCatalog();
    if (firstCatalog === "error") {
      assert.equal((await elements(".model-item")).length, 0,
        "Failed catalog must not render cached model cards");
      await clickButton("button", "목록 새로고침");
      // An old error can remain in the DOM for a render tick after clicking.
      // Wait for the new catalog's loaded state, never treat the old error
      // as an immediate recovery failure.
      const limit = Date.now() + 12_000;
      let recovered = false;
      while (Date.now() < limit) {
        if (await catalogState() === "loaded") { recovered = true; break; }
        await sleep(200);
      }
      assert.equal(recovered, true,
        "Manual retry must recover the model catalog after transient error");
    }
    // The user never authorizes a GPU job here. Check the error/preflight path.
    await clickButton('nav[aria-label="작업 도구"] button', "이미지 생성");
    await waitText("입력 사전 검사");
    await awaitNativeReleasePolicy();
    await clickButton("button", "입력 사전 검사");
    await waitText("유효한 Safetensors 체크포인트를 선택해야 합니다.");

    // Release build must never authorize a GPU operation. Read-only checks:
    // do not click consent or native GPU controls, load weights or open dialogs.
    async function verifyReleaseSafety() {
      const buttons = await elements("button");
      const gpuActions = [];
      for (const id of buttons) {
        if ((await getText(id)).includes("GPU 생성 시작")) gpuActions.push(id);
      }
      assert.equal(gpuActions.length, 1, "Expected exactly one GPU launch control");
      assert.equal(
        await call("GET", `/element/${gpuActions[0]}/enabled`),
        false,
        "Release UI must never enable GPU generation",
      );
      for (const [css, name] of [
        ['input[aria-label="실제 GPU 추론 실행 동의"]', "GPU consent"],
        ['input[aria-label="VRAM 부족 위험 별도 동의"]', "VRAM override"],
      ]) {
        const matches = await elements(css);
        assert.equal(matches.length, 1, `Missing or duplicate ${name} checkbox`);
        assert.equal(await selected(matches[0]), false, `${name} must be unchecked`);
      }
    }
    await verifyReleaseSafety();
    // Exercise a real model-catalog refresh with NO file picker or model import.
    // The refresh may briefly disable its own button while loading.
    await clickButton("button", "모델 목록 새로고침");
    await waitText("입력 사전 검사");
    await verifyReleaseSafety();
    await clickButton('nav[aria-label="작업 도구"] button', "모델 관리");
    await waitText("로컬 모델 관리");
    // Navigation must not revive GPU consent, even without any model file.
    await clickButton('nav[aria-label="작업 도구"] button', "이미지 생성");
    await waitText("입력 사전 검사");
    await awaitNativeReleasePolicy();
    await verifyReleaseSafety();
    return {
      navigation: "passed",
      missing_checkpoint_preflight: "passed",
      release_gpu_block: "passed",
      consent_unchecked_after_navigation: "passed",
      catalog_error_recovery: firstCatalog === "error" ? "passed" : "not_exercised",
      native_release_policy: "attested_disabled",
    };
  } finally {
    try { await call("DELETE", "", undefined); } catch { /* never mask test verdict */ }
  }
}

export async function main(args = process.argv.slice(2)) {
  if (process.platform !== "win32") throw new Error("M3-26 native GUI checks require Windows.");
  if (!args.includes("--run")) throw new Error("Explicit --run flag is required; no GUI launched.");
  const app = process.env.AIIMAGE_E2E_APP;
  if (!app || !isAbsolute(app) || !app.toLowerCase().endsWith(".exe"))
    throw new Error("AIIMAGE_E2E_APP must be an absolute .exe path to a release build.");
  const path = resolve(app);
  await access(path);
  const driverBinary = process.env.AIIMAGE_TAURI_DRIVER || "tauri-driver";
  // Read-only user-created tool on PATH; no shell interpolation, auto-install or escalation.
  const { port, nativePort, url } = await allocateDriverPorts();
  const driver = spawn(driverBinary, ["--port", String(port), "--native-port", String(nativePort)],
    { stdio: "ignore", shell: false, windowsHide: true });
  let driverFailed = null;
  driver.on("error", () => { driverFailed = "start_failed"; });
  driver.on("exit", () => { driverFailed = "exited"; });
  try {
    await waitForDriver(url, 30_000, () => driverFailed !== null);
    if (driverFailed) throw new Error("Tauri WebDriver failed to start.");
    const result = await runWindowsUiSmoke(url, path);
    process.stdout.write(`M3-30 native Windows GUI checks passed: ${JSON.stringify(result)}\n`);
  } finally {
    if (driver.exitCode === null) driver.kill();
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch(error => {
    // No source paths, prompts or user files are ever printed.
    console.error("M3-26 Windows native UI smoke failed:", error?.message?.slice(0, 200));
    process.exitCode = 1;
  });
}
