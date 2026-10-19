# M3-43 — Reject an older Windows NSIS installer without changing user data

## Scope and verified prerequisites

M3-41 [ordinary CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39180152438)
and [actual Windows installed NSIS QA](https://github.com/nalkarowndal/tyrfghx/actions/runs/39180117116)
passed, including same-version repair, restarted read-only Python API,
user model/output fixture preservation and post-uninstall checks.

M3-42 built a two-version 0.1.0 -> 0.1.1 upgrade QA path and passed
[its ordinary CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39181528247).
Its actual two-version installed Windows job
[39181528220](https://github.com/nalkarowndal/tyrfghx/actions/runs/39181528220)
was **still running** at the last checkpoint when M3-43 development began.
Do not claim M3-42 installation upgrade success unless that real job
has finished with the specific successful marker.

M3-43 adds a new rejection test for an older installer **after** the
two-version upgrade has completed on a disposable Windows GitHub runner.
It does not implement a rollback routine. Failing closed against an
attempted downgrade is the correct first defense for invalid/older
upgrade attempts.

## Test-only behavior

1. Keep the production Tauri version `0.1.0` and all default Cargo
   and Windows capabilities unchanged.
2. The disposable build overlay
   `src-tauri/tauri.downgrade-guard-qa.conf.json` contains **only**
   `bundle.windows.allowDowngrades=false`; apply it to both temporary
   unsigned 0.1.0 and 0.1.1 NSIS installer builds. The resulting app
   remains the bundled **read-only** Python API, with GPU jobs disabled.
3. Normal Windows CI checks that the overlay cannot override other
   settings. It never launches an installer or application.
4. The isolated Windows packaged-backend CI first installs 0.1.0,
   performs same-version 0.1.0 repair, then upgrades using the separate
   0.1.1 `/S /UPDATE` installer. Require the Windows HKCU registered
   `DisplayVersion` to be `0.1.1`.
5. BEFORE any app window or backend process is started, execute the
   previous 0.1.0 setup again with `/S /UPDATE`. This must return a
   **non-zero exit code**, establishing rejected downgrade rather than
   success.
6. Check the installed HKCU registration is still `0.1.1`; the
   desktop executable, Python backend executable and uninstaller all
   exist and retain exactly their pre-attempt SHA-256; the read-only
   Python backend manifest still verifies; and synthetic model/output
   fixtures are byte-identical to before the attempt.
7. Only after this safety test passes, run the existing real installed
   Windows GUI authentication, backend crash/restart-button exercise,
   parent/job cleanup and interactive-uninstall data preservation.
8. Never upload or publish either installer, sign a release, invoke
   CUDA/PyTorch, download models, read owner weights, or change `main`.

These assertions are **strict**: a zero-exit older installer, a changed
registry version, changed binaries, missing backend files, changed
model/output fixtures, or a stopped backend manifest check fails QA.
This does not claim recovery from an interrupted mid-write upgrade;
that remains an independent crash-injection and transaction design task.

## Acceptance signals

Normal CI must pass with:

```text
upgrade_config_qa: safe_version_overlay_only
upgrade_config_qa: older_installer_downgrade_guard_enabled
```

The completed hosted Windows packaged-backend workflow must include:

```text
installed_qa: two_version_0_1_0_to_0_1_1_upgrade_preserved_backend_models_and_outputs
installed_qa: older_0_1_0_downgrade_rejected_0_1_1_payload_and_data_unchanged
installed_qa: installed_gui_restart_click_reconnected_and_no_orphans
installed_qa: interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs
```

`main` remains untouched and PRs remain Draft.

## Known limitations

The older/newer Windows installers differ only in version metadata
and use the same source and backend. This verifies downgrade rejection
and on-disk preservation on a disposable hosted runner, **not** full
versioned schema migration, actual rollback after a partially failed
upgrade, automatic updater signatures, SmartScreen, clean-user Windows
upgrades, offline WebView2 provisioning or owner RTX 2060 SUPER GPU
inference. A SHA-256 check alone is not an authenticity signature.

Official sources:
- https://v2.tauri.app/distribute/windows-installer/
- https://tauri.app/reference/config/
- https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi
