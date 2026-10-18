/**
 * M3-34 opt-in REAL Windows Tauri release-UI smoke (external or embedded WebDriver).
 * No downloaded models, model imports, GPU consent, screenshots or raw DOM logs.
 * A release binary deliberately disables GPU jobs. Run ONLY with --run.
 *
 * Official reference: https://v2.tauri.app/develop/tests/webdriver/
 */
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { access, writeFile, rm } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import { tmpdir } from "node:os";
import { isAbsolute, resolve, dirname, join } from "node:path";
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
/**
 * Never start an arbitrary executable from an environment-supplied filename.
 * Both Windows E2E modes may launch only the release executable in this checkout.
 */
export function isExpectedReleaseApp(candidate, root = process.cwd()) {
  if (typeof candidate !== "string" || !isAbsolute(candidate)) return false;
  const expected = resolve(root, "src-tauri", "target", "release", "aiimage.exe");
  return resolve(candidate).toLowerCase() === expected.toLowerCase();
}
const ELEM = "element-6066-11e4-a52e-4f735466cecf";
const sleep = ms => new Promise(done => setTimeout(done, ms));

// WebDriver protocol error codes are a fixed vocabulary. Never include
// arbitrary server-supplied strings (which may contain private file paths).
const WEB_DRIVER_CODES = new Set([
  "session not created", "unknown command", "unknown error",
  "invalid argument", "invalid session id", "no such element",
  "element not interactable", "stale element reference",
  "timeout", "script timeout", "unsupported operation",
  "session not found",
]);
export function safeWebDriverErrorCode(code) {
  return typeof code === "string" && WEB_DRIVER_CODES.has(code)
    ? code : "protocol_error";
}
export function describeNativeSessionProblem(code) {
  if (code === "session not created") {
    return "native_session_not_created: inspect isolated release startup probe and WebView2 attach";
  }
  return `webdriver_${safeWebDriverErrorCode(code).replaceAll(" ", "_")}`;
}

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
    const code = safeWebDriverErrorCode(payload?.value?.error);
    throw new Error(category === "session" && code === "session not created"
      ? "WebDriver session rejected: " + describeNativeSessionProblem(code)
      : `WebDriver ${category} rejected request: ${code}`);
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

export async function runWindowsUiSmoke(base, application, { embedded = false, catalogFaultMarker = null } = {}) {
  // Launching a native Windows WebView2 process often exceeds a typical
  // fast DOM-command timeout; keep startup bounded but distinct from it.
  const session = await requestWebDriver(base, "POST", "/session", {
    capabilities: { alwaysMatch: embedded ? {} : { browserName: "wry", "tauri:options": { application } } },
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
    if (catalogFaultMarker !== null) {
      assert.equal(embedded, true, "Synthetic catalog fault requires embedded E2E");
      // Wait for the initial catalog request to settle before arming the fault.
      // The hosted disposable Windows runner intentionally has no model files.
      await waitText("표시할 모델이 없습니다.");
      // Exactly one disposable marker created AFTER app startup, no model changes.
      await writeFile(catalogFaultMarker, "aiimage-e2e-fail-once\n", { flag: "wx", mode: 0o600 });
    }
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
    let firstCatalog;
    if (catalogFaultMarker !== null) {
      // An old "empty" state may persist for a React render tick after click.
      // Require actual error UI, not the first settled-looking string.
      const until = Date.now() + 12_000;
      while (Date.now() < until) {
        if (await catalogState() === "error") { firstCatalog = "error"; break; }
        await sleep(200);
      }
      assert.equal(firstCatalog, "error",
        "Test-only native fault must produce actual model catalog error");
    } else {
      firstCatalog = await awaitCatalog();
    }
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
  if (!isExpectedReleaseApp(app))
    throw new Error("AIIMAGE_E2E_APP must point to the approved release executable in this checkout.");
  const path = resolve(app);
  await access(path);
  const embedded = args.includes("--embedded");
  const injectCatalogFault = args.includes("--catalog-fault-once");
  if (injectCatalogFault && !embedded)
    throw new Error("Catalog fault E2E is available only for embedded test-only builds.");
  const catalogFaultMarker = injectCatalogFault
    ? join(tmpdir(), `aiimage-e2e-catalog-${randomUUID()}.sentinel`) : null;
  const { port, nativePort, url } = await allocateDriverPorts();
  const driverBinary = process.env.AIIMAGE_TAURI_DRIVER || "tauri-driver";
  // Embedded mode starts ONLY this validated release app, with feature-gated
  // in-app WebDriver opt-in. No external EdgeDriver or tauri-driver is needed.
  const child = embedded
    ? spawn(path, [], {
        cwd: dirname(path),
        env: {
          ...process.env,
          AIIMAGE_E2E_ENABLE: "1",
          TAURI_WEBDRIVER_PORT: String(port),
          ...(catalogFaultMarker && { AIIMAGE_E2E_CATALOG_FAILURE_MARKER: catalogFaultMarker }),
        },
        stdio: "ignore", shell: false, windowsHide: true,
      })
    : spawn(driverBinary, ["--port", String(port), "--native-port", String(nativePort)],
        { stdio: "ignore", shell: false, windowsHide: true });
  let failed = null;
  child.on("error", () => { failed = "start_failed"; });
  child.on("exit", () => { failed = "exited"; });
  try {
    await waitForDriver(url, embedded ? 60_000 : 30_000, () => failed !== null);
    if (failed) throw new Error("Windows WebDriver child exited before readiness.");
    const result = await runWindowsUiSmoke(url, path, { embedded, catalogFaultMarker });
    process.stdout.write(`M3-33 ${embedded ? "embedded" : "external"} Windows GUI passed: ${JSON.stringify(result)}\n`);
  } finally {
    if (catalogFaultMarker) {
      // Remove ONLY this run's random disposable temp marker if not consumed.
      try { await rm(catalogFaultMarker, { force: true }); } catch {}
    }
    if (child.exitCode === null && child.pid) {
      if (embedded) {
        // Terminate exactly the process tree this smoke started.
        const cleaner = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"],
          { stdio: "ignore", shell: false, windowsHide: true });
        await new Promise(resolve => {
          cleaner.once("error", resolve);
          cleaner.once("exit", resolve);
        });
      } else {
        child.kill();
      }
    }
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch(error => {
    // No source paths, prompts or user files are ever printed.
    console.error("M3-32 Windows native UI smoke failed:", error?.message?.slice(0, 200));
    process.exitCode = 1;
  });
}
