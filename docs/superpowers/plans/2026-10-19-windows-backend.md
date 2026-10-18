# Windows Backend Implementation Plan

**Goal:** Package the existing read-only FastAPI service and supervise it from Tauri on Windows.
**Architecture:** PyInstaller onedir resource, private pipe bootstrap/lease, authenticated loopback API, Rust-owned Windows job.
**Tech Stack:** Python 3.12, FastAPI/Uvicorn, Tauri 2, Rust, React/TypeScript.
**Spec:** `docs/M3_WINDOWS_BACKEND_BUNDLE.md`.
**Execution:** Inline using executing-plans and test-driven-development; the user authorized design, implementation, tests and a stacked Draft PR.

## Global constraints
- Preserve existing generation consent and release GPU prohibition.
- Do not download models or alter existing user data; QA uses temporary synthetic files.
- Base on M3-38, never merge main. Keep lockfiles and WebDriver isolation.
- No authentication token in argv, environment, disk, logs or webview.

## Review focus
- Broken/partial readiness messages must time out and release the child.
- A failed cleanup must block replacement processes.
- Two application windows/processes must not claim the same backend ownership.
- Unicode/space-containing model and bundle paths must work without shell interpolation.
- Data must survive stop, restart and packaging; installer does not own LocalAppData.

## Tasks
1. Add behavioral HTTP security tests and process smoke QA; run red. Implement
   `create_app(model_root, token)` and private-pipe server with named mutex and
   EOF shutdown. Preserve the browser development app. Run API and process tests.
2. Add Rust readiness/protocol and Windows process tests. Implement BackendManager
   with fixed executable, bounded readiness/HTTP, serialized lifecycle, cleanup
   verification and explicit restart. Wire `backend_status`, `restart_backend`,
   `bundled_backend_enabled`; keep the token native. Test with the frozen binary.
3. Add frontend IPC routing/retry tests, implement desktop status refresh and safe
   retry display while retaining the native model catalog. Run build and Vitest.
4. Add Windows PyInstaller build script, pinned packaging requirements, Tauri
   resources overlay and Windows QA workflow. Run source tests, frozen process
   smoke, Rust lifecycle integration, locked NSIS build and payload/hash guards.
5. Review the whole diff, fix verified defects, create stacked Draft PR and report
   exact check results and remaining gaps. No unverified completion claims.

## Execution record
- Repository recovered through GitHub connector because executor proxy cannot connect.
  All 146 files reproduce upstream tree `ea067761b700fea5c3d2c17f41cc8a9803b1aa12` exactly.
  Original commit object reconstructed and verified, shallow history rooted at M3-38.
- Local npm offline install failed (missing yallist cache); pip cannot install pytest;
  Rust toolchain absent. Use available Python runtime for new unittest checks and
  GitHub Actions for complete suites and Windows compilation. These are environment
  limitations, not passing tests.
