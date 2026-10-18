# M3-38 — Opt-in unsigned Windows NSIS installer build QA

## Scope and previous evidence

This milestone adds **installer build readiness** for the aiimage Windows desktop shell. It does not create a public release, ship a working Python inference backend, install the package or validate generation on the owner's RTX 2060 SUPER.

- M3-37 [regular CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39141297449) passed all four jobs.
- M3-37 [real Windows catalog failure/retry E2E](https://github.com/nalkarowndal/tyrfghx/actions/runs/39141297407) was still running when this milestone began. Do **not** claim actual model catalog recovery success without its completed log.
- Official Tauri Windows NSIS / WiX packaging guidance: https://v2.tauri.app/distribute/windows-installer/

## Design boundaries

1. Keep `src-tauri/tauri.conf.json` untouched with `bundle.active=false` and production security capability `default` only.
2. Add the tiny opt-in overlay `src-tauri/tauri.nsis-qa.conf.json`, setting **only** `bundle.active=true` and `targets=["nsis"]`. No E2E capability, WebDriver plugin, sidecar or signing override.
3. A new read-only PowerShell validator `scripts/windows-nsis-bundle-qa.ps1` checks the baseline settings, overlay structure and Cargo default-feature policy **without** creating or executing files by default.
4. The Windows workflow is opted in only by a maintainer's same-repository `run-nsis-bundle-qa` PR label, or via explicitly confirmed manual dispatch (once available on the default branch). The workflow does not have a GitHub write token.
5. A real hosted Windows build uses locked npm and Cargo dependency graphs and runs:

   ```powershell
   npm ci --no-fund
   npm run tauri -- build --bundles nsis --config src-tauri/tauri.nsis-qa.conf.json
   ./scripts/windows-nsis-bundle-qa.ps1 -VerifyBundle
   ```

6. The workflow requires the **normal Cargo dependency tree** to exclude `tauri-plugin-wdio-webdriver`, reads a single generated NSIS `aiimage*-setup.exe` in the fixed `src-tauri/target/release/bundle/nsis` folder, checks a PE `MZ` header and reports its SHA-256. A hash is **not** an authenticity signature.
7. Never run the installer, install any software, upload the installer as an Action artifact, create a release, import secrets or sign code. The CI output is an **unsigned ephemeral build**, not downloadable software offered to users.
8. Ordinary Windows Rust CI validates the settings but does **not** bundle anything.

## Important incomplete features

- The NSIS package contains the Tauri/React frontend shell, **not a packaged FastAPI/Python backend, custom nodes, model store or CUDA inference toolchain**. Its existence is not evidence that users can generate images or video after installation.
- No installer launch/uninstall behavior, clean-machine compatibility, admin/UAC behavior, WebView2 download, icon appearance, virus scan, Windows SmartScreen or code signing is verified.
- Normal release builds continue to block native GPU jobs by policy.
- No private model files or existing installations are read or changed.
- The temporary NSIS build should not be distributed for practical use. End-user distribution needs packaging design, signing and a separately authorized release QA process.

## Acceptance checklist

- [ ] Static overlay and production isolation checks pass on Windows CI.
- [ ] GitHub Actions completes real unsigned NSIS build.
- [ ] Exact one NSIS executable is present and passes PE/size/hash checks.
- [ ] Cargo.lock remains unchanged and normal dependency graph excludes embedded WebDriver.
- [ ] No signed, installed, released, uploaded or GPU-enabled artifact is produced.

Record successes only after those specific GitHub Actions jobs finish.
