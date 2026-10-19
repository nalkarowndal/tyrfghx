# M3-44 — Deterministic NSIS preinstall failure, unchanged installation and clean retry

## Verified upstream evidence

M3-42 [real Windows two-version upgrade QA #39181528220](https://github.com/nalkarowndal/tyrfghx/actions/runs/39181528220)
**completed successfully**, with actual registry/version checks, preservation of
the packaged read-only Python backend and model/output fixture contents, a
genuine installed GUI backend restart and safe uninstallation.

M3-43 [ordinary CI #39182315966](https://github.com/nalkarowndal/tyrfghx/actions/runs/39182315966)
also passed all four jobs. M3-43 [actual Windows downgrade rejection run #39182280355](https://github.com/nalkarowndal/tyrfghx/actions/runs/39182280355)
was still running at the start of M3-44; independent acceptance for
the attempted downgrade must be based on its completed log.

## What this milestone tests

The M3-44 test uses **one special unsigned NSIS hook** to simulate a
deterministic installer failure **before the installer copies a file,
changes the registry or creates shortcuts**.

- A test-only Tauri config
  `src-tauri/tauri.preinstall-fault-qa.conf.json` sets **only**
  `bundle.windows.nsis.installerHooks`. This overlay is used only in
  the disposable GitHub Windows packaged-backend QA workflow.
- The hook `src-tauri/nsis/m3-44-preinstall-fault.nsh` includes the
  original `nsis/preserve-data.nsh` using the documented
  `${__FILEDIR__}` include path, retaining the precise
  `NSIS_HOOK_PREUNINSTALL` protection that overrides the uninstall
  data-deletion checkbox.
- The new `NSIS_HOOK_PREINSTALL` checks the process-only CI flag
  `AIIMAGE_M3_44_ABORT_PREINSTALL`. When its value is exactly `1`
  it executes `SetErrorLevel 83` followed by `Quit`. Otherwise the
  installer behaves normally. This hook is **not included in the
  ordinary Windows installer or the production Tauri configuration**.
- The ordinary Rust Windows CI runs a *read-only* PowerShell guard that
  checks the hook's static shape, the version/downgrade overlays, and
  that the existing backend config still points to the original
  model/output preservation hook.

After the two-version 0.1.0 -> 0.1.1 installed update and M3-43's older
installer downgrade rejection check, the M3-44 hosted CI script:

1. Records SHA-256 of the owned test app, packaged Python server and
   uninstaller, plus the registered `DisplayVersion=0.1.1`.
2. Sets the **current test PowerShell process's** preflight-abort flag,
   runs the **same** 0.1.1 unsigned setup with `/S /UPDATE`, requires the
   deterministic nonzero exit code **83**, and clears the environment
   flag in a `finally` clause.
3. Requires the original 0.1.1 version registration, all three executable
   SHA-256 values, every file in the backend's generated package manifest
   and both synthetic model/output fixtures to remain unchanged.
4. Executes the same setup again, now with the abort flag removed;
   requires success, the same registered version and the expected
   executable/backend hashes and synthetic fixtures.
5. Repeats all real installed GUI tests: backend authentication, actual
   restart-button click following an owned backend failure, parent
   process crash cleanup and interactive uninstall while preserving both
   synthetic model/output files.

The feature-gated WebDriver server is never bundled. The Python API
remains read-only, and GPU inference is always disabled for this release
configuration. CI never touches the user's Windows installation or real
model files, never uploads installers, never signs/releases a binary,
and never merges to `main`.

## Acceptance

The final GitHub Windows job **must** contain:
```text
installed_qa: two_version_0_1_0_to_0_1_1_upgrade_preserved_backend_models_and_outputs
installed_qa: older_0_1_0_downgrade_rejected_0_1_1_payload_and_data_unchanged
installed_qa: preinstall_failure_preserved_current_version_backend_and_data
installed_qa: preinstall_failure_followed_by_clean_retry_and_preservation
installed_qa: installed_gui_restart_click_reconnected_and_no_orphans
installed_qa: interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs
```

Mock Node tests or normal CI alone are **insufficient** to assert these real
Windows NSIS conditions passed.

## Not a transaction rollback

Because the failure occurs in `NSIS_HOOK_PREINSTALL`, **before copying or
modifying installation data**, this tests a fail-closed early-preflight
failure and a successful later retry. It does **not** establish rollback
after a power loss, failed file replacement, incomplete database migration
or other partial installation. A true transactional rollback needs
a separate staging/backup design, carefully controlled crash injection,
restore verification and clean-VM matrix.

This also does not validate an end-user signed Tauri Updater package,
SmartScreen, real Windows PC installation, offline WebView2, GPU/CUDA
inference or the owner's RTX 2060 SUPER 8GB device.

Official sources:
- https://v2.tauri.app/distribute/windows-installer/
- https://tauri.app/reference/config/
- https://nsis.sourceforge.io/Docs/Chapter4.html
