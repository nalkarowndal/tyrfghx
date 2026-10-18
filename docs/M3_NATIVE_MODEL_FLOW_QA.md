# M3-25 — Synthetic model flow integration QA and manual Windows acceptance

M3-25 exercises the complete **local model-management data flow** with
harmless synthetic files. It does **not** claim real GUI E2E coverage, CUDA
execution, official model provenance, or successful image generation.

## Automated regression tests

- **Windows Rust test**: creates a tiny local safetensors-header fixture,
  imports it into the fixed repository-local model root, confirms the source
  stays intact, reads it from the native catalog, verifies its recorded hash,
  modifies the copied file **without changing its byte length**, and checks
  that the explicit SHA-256 rehash reports `mismatch`. Importing again refuses
  to overwrite. No real checkpoints or GPUs are accessed.
- **Native catalog edge cases**: importing two identical-byte fixtures yields
  a cautious duplicate hint. A manually placed, unregistered safetensors
  appears in the catalog but hashes as `not_recorded` (the tool does not
  silently hash unregistered files). Legacy CKPT input remains refused.
- **React server-render smoke**: checks that the per-model SHA-256 action is
  available for safe file formats in Tauri UI, not the browser-only UI or
  legacy CKPT. This only tests static rendering, **not clicks or native GUI**.
- **Python fixture tests**: check exclusive creation, bounded header,
  well-labeled no-model payload, unsafe format refusal and symlink rejection
  where supported.

CI: `npm ci && npm run build && npm test`, plus
`cd backend && python -m pytest -q` on Linux/Windows and
`cargo test --manifest-path src-tauri/Cargo.toml --lib` on Windows.

## Owner-run Windows GUI acceptance (still required)

On the **developer machine**, using an ordinary terminal in this repository:

1. Run `npm ci` and `.\\scripts\\windows-dev.ps1`. Fix reported prerequisites
   yourself; the checker installs nothing. See [Windows launcher](M3_WINDOWS_DEV_LAUNCH.md).
2. Optionally create a **harmless non-model** file with
   `python backend/qa_fixture.py`. It creates a tiny, clearly labeled
   `qa-fixtures/m3-25-ui.safetensors` using exclusive creation; repeated
   execution refuses to overwrite it. This is NOT a GPU-ready model.
3. Explicitly run `.\\scripts\\windows-dev.ps1 -Start`. Check whether the
   actual Windows Tauri development window opens and stays responsive.
4. Open **모델 관리**. Select **체크포인트** and import the test file through
   the OS file picker. Confirm the source remains unchanged.
5. Confirm that the new model is visible after refresh while the Python
   backend is stopped; it should show an unknown architecture/family.
6. Click **현재 파일 SHA-256 검증** for this test item. Confirm a
   point-in-time **일치** result and no untrusted local paths in errors.
7. Confirm that selecting the same source again refuses overwrite. Make no
   changes to real private models. Use the automated Rust fixture test for
   tamper/mismatch testing unless you are working on a disposable test copy.
8. Open **이미지 생성** and confirm that the QA-only fixture is **not treated as
   a proven runnable SDXL checkpoint**. Do **not** check GPU consent or run
   any GPU operation as part of this smoke test.
9. Separately record outcomes **passed**, **failed** or **not tested**, with
   operator-provided details. The app does not automatically claim GUI QA
   succeeded, and no screenshot/logs are uploaded.

The tests cannot guarantee a model is safe, that its hash was authenticated by
the publisher, or that its checkpoint/LoRA compatibility works. Inspect GPU
hardware readiness with the separate **opt-in** M3-10/M3-18 tools only on the
actual RTX 2060 SUPER 8 GB PC when authorized.

## Future (not completed in M3-25)

- True Windows UI click-through automation. The official
  [Tauri WebDriver guide](https://v2.tauri.app/develop/tests/webdriver/)
  describes WebdriverIO with `@wdio/tauri-service`; it requires separate
  dependency, native binary and CI integration, and cannot be claimed present
  by these Rust/SSR smoke tests.
- Unified release-time model root with the Python sidecar and safe lifecycle
  / authentication (tracked in issue #25).
- Windows installer, production inference enablement and real GPU acceptance.

Tests use synthetic data and do not access or upload user files.
