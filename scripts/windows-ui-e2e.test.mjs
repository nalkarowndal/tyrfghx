import { after, test } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { runWindowsUiSmoke, requestWebDriver, waitForDriver } from "./windows-ui-e2e.mjs";

const ELEMENT = "element-6066-11e4-a52e-4f735466cecf";
const makeResponse = (reply, status = 200) => ({
  code: status, payload: JSON.stringify({ value: reply }),
});

async function fakeDriver({ gpuEnabled = false, showPreflight = true } = {}) {
  let screen = "generation";
  let preflight = false;
  let closed = false;
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    let payload = {};
    try { payload = JSON.parse(Buffer.concat(chunks).toString() || "{}"); } catch {}
    const url = req.url || "";
    let response;
    if (url === "/status") response = makeResponse({ ready: true });
    else if (url === "/session" && req.method === "POST") {
      assert.equal(payload.capabilities.alwaysMatch["tauri:options"].application, "C:\\fake\\aiimage.exe");
      response = makeResponse({ sessionId: "a1234567", capabilities: {} });
    } else if (url === "/session/a1234567" && req.method === "DELETE") {
      closed = true; response = makeResponse(null);
    } else if (url === "/session/a1234567/elements" && req.method === "POST") {
      let ids = [];
      if (payload.value === "body") ids = ["body"];
      else if (payload.value.startsWith("nav[")) ids = ["nav-model", "nav-image"];
      else if (payload.value === "button") ids = ["refresh", "preflight", "gpu"];
      response = makeResponse(ids.map(id => ({ [ELEMENT]: id })));
    } else if (url.startsWith("/session/a1234567/element/")) {
      const [, id, operation] = url.slice("/session/a1234567/element/".length).split("/");
      if (operation === "text") {
        const names = {
          "nav-model": "모델 관리", "nav-image": "이미지 생성", refresh: "목록 새로고침",
          preflight: "입력 사전 검사", gpu: "GPU 생성 시작 (개발판 전용)",
        };
        let body = "aiimage ";
        body += screen === "models" ? "로컬 모델 관리 데스크톱 모델 가져오기" : "이미지 생성 입력 사전 검사";
        if (screen === "generation" && preflight && showPreflight) {
          body += " 유효한 Safetensors 체크포인트를 선택해야 합니다.";
        }
        response = makeResponse(id === "body" ? body : names[id] ?? "");
      } else if (operation === "click") {
        if (id === "nav-model") screen = "models";
        if (id === "nav-image") screen = "generation";
        if (id === "preflight") preflight = true;
        if (id === "gpu") throw Error("Unsafe GPU click forbidden in E2E");
        response = makeResponse(null);
      } else if (operation === "enabled") {
        response = makeResponse(id === "gpu" ? gpuEnabled : true);
      } else {
        response = makeResponse({ error: "unknown command" }, 404);
      }
    } else response = makeResponse({ error: "unknown command" }, 404);
    res.writeHead(response.code, { "content-type": "application/json" });
    res.end(response.payload);
  });
  await new Promise(done => server.listen(0, "127.0.0.1", done));
  const addr = server.address();
  return { url: `http://127.0.0.1:${addr.port}`, get closed() { return closed }, close: () => new Promise(done => server.close(done)) };
}

test("M3-26 protocol: actual model-navigation and safe preflight command order", async () => {
  const server = await fakeDriver();
  try {
    await waitForDriver(server.url, 500);
    const checks = await runWindowsUiSmoke(server.url, "C:\\fake\\aiimage.exe");
    assert.deepEqual(checks, {
      navigation: "passed", missing_checkpoint_preflight: "passed", release_gpu_block: "passed",
    });
    assert.equal(server.closed, true, "session must always close");
  } finally { await server.close(); }
});

test("M3-26 release safety: fail if GPU start is enabled without clicking it", async () => {
  const server = await fakeDriver({ gpuEnabled: true });
  try {
    await assert.rejects(runWindowsUiSmoke(server.url, "C:\\fake\\aiimage.exe"), /Release UI must never enable GPU/);
    assert.equal(server.closed, true);
  } finally { await server.close(); }
});

test("M3-26 UI failure: missing checkpoint message causes hard failure and session cleanup", async () => {
  const server = await fakeDriver({ showPreflight: false });
  try {
    await assert.rejects(runWindowsUiSmoke(server.url, "C:\\fake\\aiimage.exe"), /Expected safe UI marker absent/);
    assert.equal(server.closed, true);
  } finally { await server.close(); }
});

test("M3-26 WebDriver API returns protocol error category without leaking raw payload", async () => {
  const server = await fakeDriver();
  try {
    await assert.rejects(requestWebDriver(server.url, "POST", "/invalid", {}), /unknown command/);
  } finally { await server.close(); }
});
