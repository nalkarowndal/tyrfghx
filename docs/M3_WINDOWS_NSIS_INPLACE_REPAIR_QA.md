# M3-41 — Windows NSIS same-version repair and preservation QA

## Scope

This milestone tests an **in-place same-version repair** using the same unsigned
NSIS installer on an isolated, disposable GitHub-hosted Windows runner. It is
**not** a version-to-version upgrade, an updater plugin integration, a signed
distribution, or an installation on the owner's computer.

Tauri's Windows NSIS script supports the `/UPDATE` option. In update mode it
skips the ordinary previous-install uninstall path. This is independently
documented by the authoritative source:
https://github.com/tauri-apps/tauri/blob/dev/crates/tauri-bundler/src/bundle/windows/nsis/installer.nsi
and its Windows installer guide:
https://v2.tauri.app/distribute/windows-installer/

## Security constraints

- No new application runtime code or Cargo feature is introduced.
- No embedded HTTP WebDriver is linked into the normal bundled production app.
- The QA script still requires `GITHUB_ACTIONS=true` and
  `RUNNER_OS=Windows`. It refuses to start when a pre-existing
  `%LOCALAPPDATA%/com.aiimage.studio` directory is present.
- Its target is an unpredictable, runner-temp installation path. It creates only
  two synthetic fixtures in the fresh disposable app-data directory:
  `models/qa-preserve.txt` and `outputs/qa-preserve.txt`.
- A first NSIS `/S /D=<runner-temp-path>` installation is performed **before
  launching any application**. A second `/S /UPDATE /D=<same-path>` install
  repairs the existing installation without running or killing an app.
- After repair, verify that the app executable, bundled read-only Python
  backend and uninstaller remain present; both executable SHA-256 hashes are
  identical to those before repair; the backend's complete generated manifest
  still verifies; and both synthetic model/output fixtures are byte-for-byte
  unchanged. A hash check is not a code signature.
- Only after repair passes does the existing M3-40 suite exercise genuine
  installed Windows UI login, parent/child crash cleanup, the **백엔드 다시 시작**
  UIAutomation click and loopback authentication (401 without credentials).
  The previous interactive NSIS removal test then checks both synthetic
  user data fixtures survive even with the stock delete-data checkbox selected.
- Never download model weights, invoke CUDA/GPU, publish artifacts, upload
  unsigned installers, handle signing keys, overwrite a user installation, or
  merge to `main`.

## Execution and acceptance

The existing
`.github/workflows/windows-backend-bundle-qa.yml` now includes
`feat/m3-41-nsis-inplace-repair-qa` in its explicit push branch allowlist.
It uses the existing locked Python/Rust/npm dependencies, immutable model
preservation fixture, Windows Job Object ownership and unsigned NSIS
packaging.

Success needs a completed hosted Windows run containing **both**:

```text
installed_qa: same_version_update_mode_repair_preserved_app_backend_models_and_outputs
installed_qa: installed_gui_restart_click_reconnected_and_no_orphans
```

And the previous uninstall marker:

```text
installed_qa: interactive_uninstall_with_delete_checkbox_preserved_models_and_outputs
```

Normal CI also must pass its frontend, Linux/Windows Python and Windows Rust
jobs. Passing normal CI does not by itself validate an actual installer.

## Explicitly not yet proved

The same-version repair tests no version migration. A **real** upgrade will
require two distinct signed-version candidates, a clean-machine matrix,
release metadata and user data migration/rollback acceptance. Tauri's Updater
uses mandatory signatures; do not treat the local unsigned `/UPDATE` test
as updater or production-release readiness:
https://v2.tauri.app/plugin/updater/

CUDA/PyTorch/Diffusers packaging, actual image generation on RTX 2060 SUPER
8GB, GPU OOM recovery, clean-user Windows installation, SmartScreen and
genuine signed release also remain unverified.

Stacked prerequisite: M3-40 PR #42; do not claim its new restart-click
acceptance until the completed M3-40/M3-41 Windows packaged backend QA
provides that evidence.
