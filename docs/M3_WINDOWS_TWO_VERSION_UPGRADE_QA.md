# M3-42 — Real two-version Windows NSIS update-mode preservation QA

## Verified baseline

The previous M3-41 workflow completed successfully:
- [General Windows/Linux/React CI #39180152438](https://github.com/nalkarowndal/tyrfghx/actions/runs/39180152438): all four jobs passed.
- [Hosted Windows installed-app QA #39180117116](https://github.com/nalkarowndal/tyrfghx/actions/runs/39180117116): confirmed same-version `/UPDATE` repair; verified installed Python backend manifests, normal close, parent crash, actual restart-button UIAutomation recovery, and model/output fixture preservation after interactive uninstall.

M3-41 tested only the **same** installer twice. M3-42 adds a
**real two-version NSIS installation** (0.1.0 -> 0.1.1) to that disposable
hosted Windows CI workflow, without changing the shipped source project's
Tauri/Cargo package version or generating a public release.

## How two unsigned installers are built

- The baseline remains Tauri's project version `0.1.0`.
- A test-only override `src-tauri/tauri.upgrade-qa.conf.json` contains
  **only** `{"version":"0.1.1"}`. Tauri's CLI merges `--config`
  overlays in order. Both use the existing
  `src-tauri/tauri.backend-qa.conf.json` with `bundled-backend` and
  `currentUser` NSIS mode. Do not enable the embedded WebDriver feature.
- Build the 0.1.0 signed-**off**, no-release NSIS installer normally.
  Verify it and move **only** this runner's generated setup executable
  to the dedicated `RUNNER_TEMP/aiimage-m3-42-original-setup.exe` file.
- Build the newer 0.1.1 unsigned installer by passing the bundled-backend
  config and the version-only override to `tauri build`; verify the
  PE/size/SHA-256 checks and confirm Cargo/npm lockfiles remain unmodified.
- No installers are uploaded as artifacts, signed, published or copied
  outside the disposable GitHub runner.

## Actual installed-app acceptance

`scripts/windows-installed-backend-qa.ps1 -VerifyTwoVersionUpgrade`
still first refuses pre-existing `com.aiimage.studio` AppData and targets
a new random runner-temp installation directory. It then:

1. Installs `0.1.0` using `/S /D=<random install path>`.
2. Runs the existing same-version `/UPDATE` repair and checks both
   app/backend SHA-256 plus backend manifest and synthetic user data.
3. Requires the original per-user NSIS registry `DisplayVersion=0.1.0`.
4. Installs the *other* unsigned setup binary with
   `/S /UPDATE /D=<same random path>`, and requires
   `DisplayVersion=0.1.1` afterward.
5. Requires the desktop executable, backend executable and uninstaller
   to remain present, the existing packaged read-only backend SHA-256
   and manifest to remain intact, and both synthetic
   `models/qa-preserve.txt` and `outputs/qa-preserve.txt` unchanged.
6. Runs all prior installed real UI tests against **the newly installed**
   application: loopback API authentication, no duplicate children,
   normal close, parent crash, a real **백엔드 다시 시작** UIAutomation click
   after backend failure and subsequent backend process cleanup.
7. Runs the previous interactive uninstaller test and ensures both
   synthetic user data fixtures remain after the delete-data checkbox
   is selected.

The acceptance log must contain:

```text
upgrade_config_qa: safe_version_overlay_only
installed_qa: same_version_update_mode_repair_preserved_app_backend_models_and_outputs
installed_qa: two_version_0_1_0_to_0_1_1_upgrade_preserved_backend_models_and_outputs
installed_qa: installed_gui_restart_click_reconnected_and_no_orphans
installed_qa: interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs
```

Normal CI checks the version-only override and production feature
isolation without running an installer or GPU job.

## What this does NOT prove

This is a **version-metadata installer upgrade test**. Only the NSIS package
version changes; the application source logic, bundled Python server and
data schema intentionally do **not** change. It does not prove schema
migration, rollback after a failed upgrade, downgrade refusal, rollback
of changed model metadata, GitHub release-signing, Tauri Updater signatures,
clean-machine installation, SmartScreen handling, offline WebView2
provisioning, or real local RTX 2060 SUPER GPU image generation.

Tauri Updater uses mandatory cryptographic signatures and is not enabled
by this unsigned QA. Real end-user distribution remains prohibited
without a separate authorized release and signing process.

Official documentation:
- https://v2.tauri.app/distribute/windows-installer/
- https://v2.tauri.app/develop/configuration-files/
- https://v2.tauri.app/plugin/updater/
- https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi
