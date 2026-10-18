# M3-29 — Windows native UI safety E2E hardening

M3-29 extends the **explicitly opt-in** Tauri Windows release-UI smoke
introduced in M3-26. It does not run CUDA, start Python inference, open the
OS file picker, import a model, or make changes to private checkpoint files.

## What the native runner now checks

On an authorized release-build Windows Tauri app using `tauri-driver`:

1. Open the model manager, wait for an **enabled** catalog refresh button,
   and explicitly refresh the local catalog.
2. Navigate to image generation and click the input preflight button with no
   checkpoint selected. Verify the existing missing-checkpoint message.
3. Assert there is **exactly one GPU launch button** and it is disabled.
4. Assert both actual DOM controls, **실제 GPU 추론 실행 동의** and
   **VRAM 부족 위험 별도 동의**, exist once and are unchecked.
   Read them through W3C WebDriver's element `/selected` endpoint; do not
   click, tick, force-set, or otherwise authorize them.
5. Refresh the generation catalog and verify the two unchecked consents and
   disabled GPU launch control again.
6. Navigate away and return, verifying that those restrictions remain.
7. Always try to close the native WebDriver session, including after a failed
   assertion. Fail fast when the spawned driver cannot start or exits early.

The app uses W3C `browserName: wry` and a bounded wait for enabled native
controls so an initial asynchronous model lookup isn't misreported as an
unavailable button.

## Regular GitHub Actions CI: protocol tests, not GUI evidence

`node --test scripts/windows-ui-e2e.test.mjs`

The synthetic local WebDriver server checks the expected DOM and W3C command
sequence. Fail-closed scenarios include an unexpectedly enabled release GPU
action, a checked GPU consent, a checked VRAM override, a missing checkbox and
an absent preflight warning. The success case proves that a model catalog
refresh is actually requested. The session must be cleaned up even on failure.

**Passing these mock tests is not proof of a working Windows Tauri window.**
Regular PR CI continues to cover TypeScript/Vitest, Python Linux/Windows and
Windows Rust tests separately.

## Actual Windows GUI E2E — operator opt-in only

The existing `Windows native UI E2E (opt-in)` GitHub workflow remains
disabled for ordinary PRs. On an eligible same-repository PR the operator can
explicitly add the `run-native-ui-e2e` label, or use a confirmed manual
workflow_dispatch on the repository's default branch when available. This
launches an isolated hosted Windows runner and a GPU-disabled **release**
binary. Never imply local RTX 2060 SUPER results from that run.

The script can also be run by the operator on Windows after installing
compatible Tauri/Edge driver prerequisites and producing the release binary:

```powershell
npm ci
npm run tauri -- build --no-bundle
$env:AIIMAGE_E2E_APP = (Resolve-Path "src-tauri\target\release\aiimage.exe").Path
node scripts/windows-ui-e2e.mjs --run
```

No private path, screenshot, prompt or model data is uploaded by the smoke
script. Be mindful that CI logs of unrelated tools may have their own logging
policies. Use a disposable environment.

## Not yet covered

True native GUI interaction has not been observed until an opt-in hosted
Windows run succeeds. The test does not validate native model import
dialogs, SHA-256 result views for real models, recovery of a deliberately
broken model directory, signed packaging, SDXL/Anima/Illustrious compatibility,
8 GB GPU inference or image quality.

Documentation cross-check:
- https://v2.tauri.app/develop/tests/webdriver/
- https://v2.tauri.app/develop/tests/webdriver/ci/
