# M3-31 — First real Windows GUI test and native release-policy attestation

## Observed real Windows CI evidence

M3-30's normal GitHub Actions CI passed (PR #32). On 2026-10-18,
we explicitly triggered the existing **opt-in, GPU-disabled release Windows
GUI E2E** against commit `cc92fcf7`, via the `run-native-ui-e2e` PR label.

- [First real hosted Windows GUI run](https://github.com/nalkarowndal/tyrfghx/actions/runs/39132228233)
- Windows Tauri **release executable compiled successfully**.
- `tauri-driver v2.1.0` and a matching WebView2/EdgeDriver were installed.
- The **actual GUI click-through failed** with an unclassified
  `The operation was aborted due to timeout` message about 12 seconds
  after the Node runner started.
- Since the old runner never logged which WebDriver stage timed out,
  this evidence **does not establish** whether native session startup,
  page navigation, or an element request timed out. Do not claim the
  desktop GUI or catalog recovery passed.

## Fix and hardening

1. Separate Windows-native session creation from quick DOM requests. W3C
   `POST /session` now has a bounded **90-second** timeout, while a normal
   DOM command keeps its 12-second timeout and status probing uses 4 seconds.
2. Failures report only `status`, `session`, `command` or `other`
   request category and timeout / sanitized W3C protocol error, never
   private filenames, prompts, app paths, session tokens or raw DOM text.
3. Add an actual Tauri IPC-based release policy status to the generation UI:
   - `checking`: command has not returned;
   - `disabled`: native command confirmed the release GPU runner is disabled;
   - `enabled`: debug runner is available; still requires explicit consent;
   - `error`: native command failed; launch remains blocked;
   - `browser`: no native runner is present.
4. Native GUI E2E now waits specifically for the verified
   `로컬 GPU 실행 정책 확인됨: 배포판 비활성` state. A merely disabled
   GPU launch button is insufficient because missing model, missing consent
   or preflight failures can disable the same button in a debug build.
   An unexpectedly enabled runner or failed native policy IPC fails closed.
5. Add Vitest policy-contract checks and synthetic W3C tests for native
   startup delays, safe timeout categories, enabled debug policies, and
   rejected native policy IPC.

## Reverification and limits

Normal PR CI must pass TypeScript/Vitest, fake local WebDriver protocol,
Linux/Windows Python and Windows Rust. These **do not** prove GUI success.

A further **explicit opt-in** GitHub Actions native Windows run must complete
successfully against the M3-31 commit to establish a working hosted Windows
GUI workflow. Neither an untested rerun nor a synthetic protocol test can
retroactively turn the first failed native run into a pass.

Native GPU inference on the owner's RTX 2060 SUPER 8 GB, packaged Python
backend, real model loading, native file picker interaction, graphical quality,
and Windows installer validation all remain outside this stage.

The test does not authorize CUDA jobs, download checkpoints, upload prompts
or screenshots, or read the owner's local files.

Official guidance:
- https://v2.tauri.app/develop/tests/webdriver/
- https://v2.tauri.app/develop/tests/webdriver/ci/
