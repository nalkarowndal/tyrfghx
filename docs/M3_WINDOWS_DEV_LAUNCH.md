# M3-22 — Windows development environment check and explicit Tauri launch

This milestone makes it easier to **open the existing Windows Tauri
development app on the owner's PC**, without confusing that task
with shipping an installer or completing actual CUDA/RTX QA.

## Recommended PowerShell workflow

Prerequisites on Windows 10/11:

- Node.js **22.12 or later** (required by current Vitest 5 and Vite 6.4) and npm; GitHub CI uses **Node 22**.
- Stable Rust with an **MSVC target** and Cargo.
- Microsoft Visual Studio C++ Build Tools, with
  **Desktop development with C++** selected.
- Microsoft Edge WebView2 Runtime (normally included in newer Windows
  versions, but version/registration must be confirmed on the target PC).
- This exact repository checkout, with `package.json` and
  `src-tauri/tauri.conf.json`.

Run the following commands yourself from the repository root.

**1. Read-only readiness inspection (default).**

~~~powershell
.\scripts\windows-dev.ps1
~~~

Or machine-readable status with **no app launch**:

~~~powershell
.\scripts\windows-dev.ps1 -AsJson
~~~

This displays which commands are installed, confirms the Rust
`windows-msvc` host toolchain, checks for the local Tauri CLI,
and cautiously checks WebView2 and MSVC installation. Unknown WebView2
or MSVC state is **check_manually**; presence of tools alone is **not
proof** the desktop GUI can be built and opened.

**2. Install frontend packages yourself, only if missing.**

~~~powershell
npm ci
~~~

Since M3-23, the repository includes a reviewed `package-lock.json`.
`npm ci` is the required reproducible frontend dependency install,
and it fails if the lockfile is missing or out of sync with
`package.json`. Do not use `npm audit fix --force` to silently change
major versions. Neither `-AsJson` nor the default check installs
dependencies or downloads anything.

**3. Explicitly open the desktop development UI.**

~~~powershell
.\scripts\windows-dev.ps1 -Start
~~~

The script refuses `-Start` when necessary prerequisites are absent,
and `-Start -AsJson` is deliberately rejected (the JSON mode is
read-only). Once explicitly started, it invokes only the existing
`npm run tauri dev` command from the repository root. Tauri's
`beforeDevCommand` starts local Vite on 127.0.0.1:5173. No arbitrary
script path or shell command comes from frontend input.

If PowerShell security policy prevents local script execution, review
the Windows PowerShell execution policy as the machine administrator;
this milestone does **not** change policy or instruct automatic bypass.

### Optional Python / SDXL GPU capability

The UI and native local model catalog can be opened **without**
`.venv\Scripts\python.exe`. The script marks an absent Python
environment as **not_configured**, not as a reason to block the UI.

To try the separate, **DEBUG-only consent-gated SDXL generator**, the
owner must additionally install Python 3.12, initialize the private
`.venv`, install optional Diffusers inference dependencies and a
compatible CUDA PyTorch build, prepare an authorized local SDXL
checkpoint and an offline SDXL config, and pass fresh native GPU/VRAM
safety preflight. The script does **not** perform any of those steps,
load GPU weights, consent to generation or probe CUDA memory.

On an RTX 2060 SUPER 8GB, use conservative 512×512 / 15-step settings
when later choosing to start a manual test; **successful inference
remains unverified**.

## CI and verified scope

GitHub Actions' `desktop-rust-windows` job now also installs npm
dependencies through the repository's existing npm-install workflow
and runs a PowerShell-only smoke test before the Rust unit tests.

The smoke test checks PowerShell syntax, read-only JSON schema,
required prerequisite categories, failure on combined
`-Start -AsJson`, consistency of missing prerequisite reporting and
the absence of automatic installer/download commands. **CI does not
invoke `-Start` or create a Windows desktop session**, and
the local PC's WebView2/MSVC state is not verified by CI.

The launcher deliberately does **not** create a release package,
enable GPU inference in release builds, download model assets,
disable Windows security settings or certify the user's device.

References:

- https://v2.tauri.app/start/prerequisites/
- https://v2.tauri.app/develop/
- https://v2.tauri.app/start/frontend/vite/
- [M3-21 gallery inspector](M3_GALLERY_IMAGE_INSPECTOR.md)
- [M3-10 hardware acceptance](M3_HARDWARE_ACCEPTANCE_CLI.md)
