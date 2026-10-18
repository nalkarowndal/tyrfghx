# M3-26 — Opt-in real Windows release UI WebDriver smoke

## Scope and evidence levels

This stage adds a **real Windows native application click-through runner**
built on Tauri's documented `tauri-driver` WebDriver protocol. The test is
**not run by the regular GitHub PR pipeline**. Regular CI exercises a fake local
WebDriver server using Node built-ins, so its green checks mean the harness's
protocol and safety logic work, **not** that an actual Windows app opened.

An independent `workflow_dispatch` action can run the real Tauri release
application on a fresh GitHub-hosted Windows machine. The release build is
intentionally **GPU-disabled**. Never infer RTX 2060 SUPER compatibility,
actual SDXL results or visual quality from any of these checks.

Official sources:
- [Tauri v2 WebDriver test guide](https://v2.tauri.app/develop/tests/webdriver/)
- [Tauri Windows WebDriver CI guide](https://v2.tauri.app/develop/tests/webdriver/ci/)

## Regular automated CI (no GUI)

`node --test scripts/windows-ui-e2e.test.mjs`

Runs a local, fake W3C WebDriver server and asserts that:
- Tauri native GUI session is created from an explicit application path;
- navigation reaches **모델 관리**, then **이미지 생성**;
- the preflight failure for a missing checkpoint is visible;
- the **GPU 생성 시작** button is present but **disabled** in a release build;
- an accidentally enabled GPU action makes the test fail *without clicking* it;
- a missing preflight error is a test failure, not a false pass;
- the session is closed even after failures.

These checks cannot drive a real native GUI or determine if Windows/WebView2
starts successfully. They install no new npm dependencies and have no network
access beyond the process-local synthetic HTTP server.

## Real GUI workflow (explicit human trigger)

Select **Actions → Windows native UI E2E (opt-in) → Run workflow** and set
`confirm_release_only=true`. GitHub then uses a fresh hosted Windows
runner to compile the Tauri RELEASE executable (no installer), install
WebDriver/Edge driver prerequisites and invoke:

```powershell
$env:AIIMAGE_E2E_APP = (Resolve-Path "src-tauri\target\release\aiimage.exe").Path
node scripts/windows-ui-e2e.mjs --run
```

Or run locally only after you have deliberately installed a matching
`tauri-driver` and Edge WebDriver, and built the release application:

```powershell
npm ci
npm run tauri -- build --no-bundle
$env:AIIMAGE_E2E_APP = (Resolve-Path "src-tauri\target\release\aiimage.exe").Path
node scripts/windows-ui-e2e.mjs --run
```

The process requires Windows, an absolute executable location and `--run`.
The runner starts a localhost WebDriver, opens the real Tauri app, checks
navigation and the missing-checkpoint preflight, validates that GPU launch is
**disabled**, and closes its WebDriver session. It does NOT click native
OS file pickers, import model files, write to the local model registry, request
GPU consent or start Python inference. No screenshots or raw app logs are
uploaded by the script. Existing app data is not modified by the script.

For manual/CI diagnostics use only allowlisted pass/fail categories. Never
share private model filenames, prompts, local account paths or user screenshots.

## What remains unproven

- Real Windows GUI E2E is `not_tested` until the separately-triggered
  GitHub Actions workflow actually succeeds.
- The legacy native file picker needs a separate explicit operator session.
  An unattended test must **not** feed arbitrary filesystem paths into Tauri.
- An actual 8 GB GPU CUDA execution/cleanup, SDXL/Anima/Illustrious/LoRA
  loading, image quality, packaged Python backend and release GPU behavior
  require separate safe acceptance procedures.
- GitHub-hosted Windows is not the end user's local Windows setup.

## Failure response

Any missing element, missing preflight warning, enabled release GPU action,
WebDriver protocol error or missing driver fails the test, and the session
cleanup runs even on a failed assertion. It never automatically retries GPU
operations or asserts that a failure recovered without a verified GUI check.
