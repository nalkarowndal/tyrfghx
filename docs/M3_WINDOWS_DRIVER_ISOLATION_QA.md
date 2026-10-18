# M3-30 — Isolated Windows WebDriver and safe model-catalog retry QA

## Scope

M3-30 hardens the **opt-in Windows Tauri release-UI smoke harness** from M3-29.
It does not introduce GPU execution, OS file-picker automation, automatic model
imports, destructive file edits, downloads or any bypass of the native safety
gates. The normal PR CI still runs only a **fake in-process WebDriver** and
cannot establish actual Windows GUI success.

### Driver isolation

The launcher previously used fixed TCP ports 4444 and 4445. If another
WebDriver instance was already listening, a new test could connect to the
wrong process and misreport results or interact with its unrelated session.

The runner now asks the OS for two distinct ephemeral **127.0.0.1** ports,
then starts `tauri-driver --port <PORT> --native-port <NATIVE_PORT>`.
It waits for the **newly started child**, checks early process failure and
uses its dedicated loopback URL for all session calls. This greatly reduces
accidental reuse of another test's driver. Like any reserve-then-bind approach,
it cannot mathematically eliminate a short race where another process binds
the port first; native GUI success therefore still needs an actual opt-in run.

### Model-list failure recovery

The real GUI smoke clicks **목록 새로고침** in **모델 관리** and waits for a
catalog result instead of immediately navigating away:

- If the screen shows model cards or a legitimate **표시할 모델이 없습니다.**
  state, continue without claiming recovery was tested.
- If it naturally shows **모델 목록 오류:**, assert that no old
  `.model-item` cards remain visible and that a user-initiated second
  **목록 새로고침** can restore a loaded state within a bounded wait.
- If that error persists, no valid state appears, stale cards remain, or a
  button never enables, **fail the test**. Do not silently count it as pass.
- Report `catalog_error_recovery: "passed"` only for a real observed failure
  followed by successful retry; otherwise report `"not_exercised"`.

The test does **not** sabotage the model directory or fabricate an error
inside the native app, because it must not modify personal model files.
Deterministic synthetic W3C protocol tests cover transient errors,
unexpected stale cards, a skipped recovery path, and early driver failure.
The native Windows release-mode checks still require the GPU button to be
disabled and consent/VRAM checkboxes to be unchecked.

## Verification

On any Node.js 22+ host, without installing an OS WebDriver:

```powershell
node --test scripts/windows-ui-e2e.test.mjs
```

Existing CI also covers TypeScript/Vitest, Linux and Windows Python and
Windows Rust regressions. All these must be distinguished from native GUI
acceptance.

To authorize a true hosted Windows GUI check, explicitly apply the
`run-native-ui-e2e` PR label to a same-repository PR or use the confirmed
manual workflow-dispatch mechanism described in
[M3-26 Windows UI E2E](M3_WINDOWS_UI_E2E.md). The workflow is skipped by
default and builds a GPU-disabled release binary. A clean run with no model
error reports `not_exercised` for the error-recovery condition.

## Remaining work

Native E2E has not run until that separate workflow succeeds. Actual RTX
2060 SUPER 8 GB GPU inference, model import dialog interactions, packaged
Python sidecar and Windows installer remain separate. No credential, private
path, prompt or screenshot is intentionally copied into test output.

References:

- Tauri WebDriver: https://v2.tauri.app/develop/tests/webdriver/
- Tauri Windows CI: https://v2.tauri.app/develop/tests/webdriver/ci/
- tauri-driver CLI port arguments: https://docs.rs/crate/tauri-driver/latest/source/src/cli.rs
