# M3-33 — Feature-gated embedded Windows WebDriver E2E

## Evidence inherited from M3-32

The previously opt-in hosted Windows run ([GitHub Actions](https://github.com/nalkarowndal/tyrfghx/actions/runs/39134585478)) proved that a GPU-disabled aiimage RELEASE executable launches and exposes a Windows main-window handle (`native_launch_probe: main_window_handle_observed`). External `tauri-driver` and EdgeDriver installation succeeded, but `POST /session` returned `native_session_not_created`. This was the third failed real native UI session, not a passing E2E test.

The [Tauri 2 WebDriver guide](https://v2.tauri.app/develop/tests/webdriver/) recommends the WebdriverIO embedded server provider; the standalone [embedded W3C plugin](https://docs.rs/crate/tauri-plugin-wdio-webdriver/latest) also supports existing direct W3C clients. M3-33 adds the latter as an **independent opt-in test route** so that we can reuse the existing safe, dependency-free Node W3C UI checks.

## Strictly test-only components

- Cargo feature `e2e-webdriver` is **optional** and default features are empty. Ordinary `npm run tauri -- build --no-bundle` does **not** link the embedded HTTP driver.
- The Rust builder registers the embedded plugin only when the feature is compiled in **and** the process environment contains `AIIMAGE_E2E_ENABLE=1` and a valid `TAURI_WEBDRIVER_PORT`. Even the special build is not automatically listening without both flags.
- Production `src-tauri/tauri.conf.json` explicitly lists only `default` capability. A second configuration file `src-tauri/tauri.e2e.conf.json` adds `webdriver-e2e` only for the test build. The test capability contains `wdio-webdriver:default` but **no general script execution, file, dialog or GPU-specific permissions**.
- This **E2E-only release executable must never be distributed, signed, uploaded as an artifact or bundled as an installer**. The embedded server exposes testing commands on loopback HTTP. It is inappropriate for production.
- Unlike official external `tauri-driver`, embedded mode launches the already-compiled Tauri application itself with a local dynamic WebDriver port. It requires **no EdgeDriver download**. Termination targets only the application tree this test launched.
- The WebDriver control sequence never invokes a GPU job, approves GPU/VRAM consent, imports model files, opens OS dialogs or captures screenshots/prompts. UI checks still require native IPC to attest that the release GPU runner is disabled.
- `src-tauri/Cargo.lock` will need to reflect the new optional dependency before final merge; the opt-in build may resolve new Cargo packages on its isolated GitHub runner.

## Tests and execution

Normal Node mock-protocol regression tests exercise **both** external and embedded W3C session handshakes without launching a Windows GUI:

```powershell
node --test scripts/windows-ui-e2e.test.mjs
```

The separately authorized hosted Windows workflow is `Windows embedded UI E2E (opt-in)`, activated only with the **run-embedded-ui-e2e** label on a same-repo PR or explicit `workflow_dispatch` confirmation once available from the default branch. It executes:

```powershell
npm ci --no-fund
npm run tauri -- build --no-bundle --features e2e-webdriver --config src-tauri/tauri.e2e.conf.json
$env:AIIMAGE_E2E_APP = (Resolve-Path "src-tauri\target\release\aiimage.exe").Path
node scripts/windows-ui-e2e.mjs --run --embedded
```

M3-33 green ordinary CI only proves the regular app and mocked protocol still work; **only a successful opt-in embedded Windows E2E run** can prove actual click-through. If plugin compilation, process startup, permission grants or DOM commands fail, report the exact safe failure category. No fallback to the older failing external driver is silently performed.

## Next acceptance areas

Real app import picker and SHA-256 controls, actual model loading, signed installers, packaged Python backend, GPU inference and image quality remain untested. Owner RTX 2060 SUPER (8 GB) acceptance is independent of hosted CI.
