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

export const DRIVER_URL = "http://127.0.0.1:4444";
const ELEM = "element-6066-11e4-a52e-4f735466cecf";
const sleep = ms => new Promise(done => setTimeout(done, ms));

export async function requestWebDriver(base, method, route, body) {
  const response = await fetch(base + route, {
    method,
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(12_000),
  });
  const payload = await response.json();
  if (!response.ok || payload?.value?.error) {
    const code = payload?.value?.error ?? "webdriver_request_failed";
    throw new Error(`WebDriver ${method} ${route}: ${String(code).slice(0, 80)}`);
  }
  return payload.value;
}

export async function waitForDriver(base, maxMillis = 30_000) {
  const deadline = Date.now() + maxMillis;
  while (Date.now() < deadline) {
    try {
      const status = await requestWebDriver(base, "GET", "/status");
      if (status?.ready !== false) return;
    } catch { /* expected before driver binds its local socket */ }
    await sleep(400);
  }
  throw new Error("Local WebDriver did not become ready.");
}

export async function runWindowsUiSmoke(base, application) {
  const session = await requestWebDriver(base, "POST", "/session", {
    capabilities: { alwaysMatch: { "tauri:options": { application } } },
  });
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
  const clickButton = async (selector, text) => {
    const ids = await elements(selector);
    for (const id of ids) {
      if ((await getText(id)).trim() === text) {
        await click(id);
        return;
      }
    }
    throw new Error(`Expected UI control absent: ${text}`);
  };

  try {
    await waitText("aiimage");
    await clickButton('nav[aria-label="작업 도구"] button', "모델 관리");
    await waitText("로컬 모델 관리");
    await waitText("데스크톱 모델 가져오기");
    await clickButton("button", "목록 새로고침");
    // The user never authorizes a GPU job here. Check the error/preflight path.
    await clickButton('nav[aria-label="작업 도구"] button', "이미지 생성");
    await waitText("입력 사전 검사");
    await clickButton("button", "입력 사전 검사");
    await waitText("유효한 Safetensors 체크포인트를 선택해야 합니다.");

    // In a release build native GPU commands are unsupported by design.
    const gpu = await elements('button[aria-label="GPU 생성 시작 (개발판 전용)"]');
    // Button has visible text rather than aria-label; verify its disabled state.
    const buttons = await elements("button");
    let foundGpu = false;
    for (const id of buttons) {
      if ((await getText(id)).includes("GPU 생성 시작")) {
        foundGpu = true;
        const enabled = await call("GET", `/element/${id}/enabled`);
        assert.equal(enabled, false, "Release UI must never enable GPU generation");
      }
    }
    assert.equal(foundGpu, true, "GPU action must be visibly disabled in release");
    await clickButton('nav[aria-label="작업 도구"] button', "모델 관리");
    await waitText("로컬 모델 관리");
    return { navigation: "passed", missing_checkpoint_preflight: "passed", release_gpu_block: "passed" };
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
  const driver = spawn(driverBinary, [], { stdio: "ignore", shell: false, windowsHide: true });
  let driverFailed = null;
  driver.on("error", e => { driverFailed = e; });
  try {
    await waitForDriver(DRIVER_URL);
    if (driverFailed) throw new Error("Tauri WebDriver failed to start.");
    const result = await runWindowsUiSmoke(DRIVER_URL, path);
    process.stdout.write(`M3-26 native Windows GUI checks passed: ${JSON.stringify(result)}\n`);
  } finally {
    driver.kill();
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) {
  main().catch(error => {
    // No source paths, prompts or user files are ever printed.
    console.error("M3-26 Windows native UI smoke failed:", error?.message?.slice(0, 200));
    process.exitCode = 1;
  });
}
