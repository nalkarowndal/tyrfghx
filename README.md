# aiimage

Local-first AI image/video creative studio for Windows. Built incrementally
with React/TypeScript/Vite (UI), Tauri 2 (desktop shell), and FastAPI (local API).

> **Current milestone: M3-29 (opt-in Windows UI safety E2E checks for catalog refresh and release consent).**
> M3-1 adds source code for an **opt-in local SDXL generation attempt**. A real
> GPU image has NOT been generated or benchmarked by this development workflow.
> Windows debug builds expose a consent-gated local Python job runner with a
> 30-minute watchdog, bounded in-memory diagnostics and Win32 Job Object process-group cancellation;
> release builds and browsers still cannot start GPU jobs. Packaged backend
> integration, driver/device validation, and native GUI testing are outstanding.

## M3-29: Windows native UI safety smoke for refresh and release GPU guards

The opt-in Windows Tauri WebDriver runner now checks that the GPU launch
button stays disabled and both the explicit GPU and VRAM-risk consent boxes
remain unchecked after real catalog refresh and navigation. It also waits
for enabled controls to avoid racing initial model loading. New Node mock
WebDriver tests fail if the controls are missing or unsafe. Regular CI
**does not run a real Windows GUI**; that requires a separate authorized
workflow. See [M3-29 Windows safety E2E](docs/M3_WINDOWS_UI_SAFETY_E2E.md).

## M3-28: catalog-bound native verification and fresh GPU consent

Late native SHA-256 or model comparison results are discarded after catalog
refresh or changed selections, so old validation does not appear for newly
loaded models. GPU and VRAM-risk consent now expire when the model catalog
snapshot changes, including a refresh that reuses the same model ID; existing
Rust GPU safeguards remain. No GPU generation occurs in these tests. See
[M3-28 catalog safety](docs/M3_CATALOG_BOUND_SAFETY.md).

## M3-27: fail-closed model catalog loading and retry

When model listing fails or a refresh begins, the UI clears its previous
checkpoint list rather than allowing stale models to remain selectable.
Superseded native IPC results are ignored, malformed payloads are rejected
and raw filesystem errors are not shown. The user can explicitly retry with
**목록 새로고침** after restoring the Python server or model directory.
See [M3-27 model catalog recovery](docs/M3_MODEL_CATALOG_RECOVERY.md).
Only synthetic/protocol CI is automated; actual Windows GUI and GPU
acceptance remain separate.

## M3-26: optional real Windows UI navigation E2E

A new native release-mode Windows `tauri-driver` script exercises actual
desktop navigation and input-preflight/error display without any GPU run.
Regular CI uses a fake W3C WebDriver server; an additional explicitly triggered
GitHub Actions workflow can build and test a real Windows Tauri **release**
binary on an ephemeral runner. A passing protocol test is NOT evidence of
Windows GUI acceptance. For the opt-in workflow, see
[M3-26 Windows UI E2E](docs/M3_WINDOWS_UI_E2E.md). Actual owner hardware
qualification and inference remain outstanding.

## M3-25: local model import → catalog → SHA-256 integration QA

Windows Rust CI now runs a synthetic on-disk flow across native import, catalog,
recorded SHA-256 recheck and same-size tamper detection; the Python backend can
generate a tiny **NOT A REAL MODEL** UI fixture without downloading weights.
React SSR smoke tests check Tauri-only verification controls. These automated
checks do **not** prove actual Windows GUI interaction or GPU success. A manual
operator checklist remains required. See [M3-25 model flow QA](docs/M3_NATIVE_MODEL_FLOW_QA.md).

## M3-24: explicitly recheck a model's SHA-256 from the desktop

The Tauri **모델 관리** page now has a per-file **현재 파일 SHA-256 검증**
button for local safetensors models. Rust reads only a pre-registered model in
the fixed model directory, streams SHA-256 under a 64 GiB limit, compares to
the import-time registry and displays match, mismatch or not-recorded.
The check is explicit, read-only, limited to one button at a time in the UI
and **not** a signed authenticity guarantee. No model weights are loaded and
no GPU job is run. See [M3-24 native integrity recheck](docs/M3_NATIVE_MODEL_INTEGRITY.md).

## What works in the codebase

- Local read-only catalog of checkpoints, LoRA and VAE safetensors files.
- Bounded header metadata reader and conservative, non-executing family hints.
- User-defined metadata via local CLI: display name, family, notes and license.
- LoRA–checkpoint family comparison (metadata *suggestion*, not loading proof).
- **Explicit local import via CLI** with a Tkinter desktop file picker, or
  `--source` for a path you select. Imports keep the source intact.
- **Native Tauri desktop model catalog:** lists local models even when the
  Python API is not running, including bounded safetensors header metadata and
  registration-time integrity snapshot hints. It has no filesystem path inputs.
- **Native Tauri desktop import button:** invokes a Rust file picker and copies
  locally. It accepts only a model category from the webview, never a path.
  The browser-only version disables this button.
- Streaming SHA-256 and optional trusted expected checksum, collision prevention,
  and locally recorded integrity snapshots.
- Locally recompute a model checksum with `--verify`. UI only displays
  recorded checksum and size/mtime snapshot changes, not live verification.
- Linux and Windows Python tests and frontend tests in GitHub Actions;
  M2-4 also adds Windows Rust build/unit-test CI.

## Generation workspace (M3-2)

Open **이미지 생성** in the React/Tauri interface to select a checkpoint,
enter prompts and seed/size settings, and run a **metadata-only input preflight**.
This preflight is not a real CUDA/image test. Windows Tauri DEBUG builds may start and cancel one GPU generation process
only with an explicit consent checkbox. Release builds and browsers cannot
start it.

The Tauri view can preview up to four of the latest local PNG images generated
by the separate CLI. Browser builds cannot read local output files; no generic
filesystem API is added. See [M3-2 generation workspace](docs/M3_GENERATION_WORKSPACE.md) and
[M3-3 Windows local job runner](docs/M3_LOCAL_JOB_RUNNER.md), plus
[M3-5 Windows process-group supervision](docs/M3_WINDOWS_PROCESS_GROUP.md).

## Install reproducible and audited Node dependencies (M3-23)

The previous Windows CI reported three known npm vulnerabilities
(1 moderate and 2 critical) originating in development-time Vitest 3
and its transitive mock/worker tooling. M3-23 upgrades to
**Vitest 5.0.5 / Vite 6.4.4**, commits an exact npm
`package-lock.json`, and uses `npm ci --no-fund` on Linux/Windows.
The initial GitHub-hosted npm audit on the updated lockfile
reported **zero known findings**. CI now runs
`npm audit --audit-level=moderate` on the locked dependency tree.

This requires **Node.js 22.12+** and does NOT enable GPU inference,
produce a packaged installer or imply that Python, Rust, CUDA and the
owner's Windows PC are security-audited. Existing explicit inference
consent remains unchanged.

Read [M3-23 dependency lock and audit](docs/M3_LOCKED_DEPENDENCY_SECURITY.md).

## Check Windows prerequisites and open the development app (M3-22)

From the repo root on Windows, run `./scripts/windows-dev.ps1` for a
**read-only check** of Node/npm, Rust MSVC toolchain, Tauri frontend
dependencies and advisory MSVC/WebView2 setup. Nothing is installed or
executed on the GPU. Use `-AsJson` for a machine-readable report,
`npm ci` yourself when frontend dependencies are missing, then
`./scripts/windows-dev.ps1 -Start` only when you explicitly want to
open the existing Tauri DEBUG development UI.

The repo **now includes a committed package-lock.json**; use
`npm ci` for deterministic frontend dependencies. This launcher is not a packaged Windows
installer, does not download Python/SDXL dependencies, and does not
auto-consent to inference. The local `.venv` is optional for opening
the UI and separately required for owner-authorized GPU attempts.

CI runs a PowerShell no-launch smoke test, not an interactive desktop
or RTX 2060 SUPER GPU test. See
[M3-22 Windows developer startup guide](docs/M3_WINDOWS_DEV_LAUNCH.md).

## Inspect generated images in the desktop gallery (M3-21)

The existing Tauri read-only PNG gallery now displays native-decoded
dimensions and lets you open a **larger inline detail inspector**.
Select a thumbnail, inspect at 50%/100%/200% size, switch between
existing locally verified images, and close with Escape. The inspector
supports normal keyboard controls and scrolls large images without
opening new windows or adding filesystem access.

No additional GPU inference, model loading, path selection, prompt
logging, image writing, downloading or remote API was introduced.
The native validator still limits filenames, image size, read scope
and gallery count. Preview does **not** certify visual quality or
that the image came from the claimed GPU.

See [M3-21 gallery image inspector](docs/M3_GALLERY_IMAGE_INSPECTOR.md).

## Independently verify generated PNG bytes during owner QA (M3-20)

The offline owner-only M3-19 review tool can now **optionally** take an
explicit `--output-root` folder, find only the fixed-format PNG
basename already claimed in the M3-10 report, and independently check
actual file bytes. The stdlib-only verifier checks an 8MiB file limit,
exact SHA-256, dimensions, full PNG chunk CRC/IEND, bounded zlib stream
and every reconstructed 8-bit RGB/RGBA scanline. It does **not**
run a model, import CUDA, query NVIDIA devices, or upload files.

The M3-19 cross-report summary remains **manual-review evidence**, not
automatic GPU hardware certification or an artistic quality score.
Without the additional output-root argument independent PNG
verification is explicitly `not_requested`. A corrupt or missing
PNG is a sanitized verification failure, never a green result.

See [M3-20 independent local PNG QA](docs/M3_INDEPENDENT_PNG_QA.md).

## Review owner-run GPU QA evidence without false qualification (M3-19)

The offline `backend/hardware_evidence_review.py` CLI can read one
**M3-10 SDXL hardware acceptance JSON** and one **M3-18 nvidia-smi
observation JSON**, with explicit `--confirm-review`. It strictly
limits input size, duplicate keys, status/measurement consistency and
file type, then reports the two source-file SHA-256 digests and only
allowlisted observations. It never invokes CUDA, loads models,
uploads any data or writes a report file automatically.

`evidence_available_for_manual_review` means only that both JSON
files **claim** a decoded image and a complete system-level
observation. They are not authenticated hardware measurements. The
real PNG pixels, process tree, RTX GPU-specific VRAM recovery, Windows
GUI, network isolation and common-session provenance all remain
`not_tested` until independently reviewed by the operator. GitHub
CI uses mocked data only.

See [M3-19 local QA evidence review](docs/M3_HARDWARE_EVIDENCE_REVIEW.md).

## Observe system VRAM on the real Windows GPU (M3-18)

A new manually operated, **read-only** CLI records sampled NVIDIA GPU
memory use while the owner separately runs or cancels a Tauri DEBUG
SDXL generation. Two explicit flags are required, observation is
limited to 10–900 seconds, and the tool does not load models or reset
drivers. It prints a bounded, sanitized summary without prompts, image
paths, user folders or raw command errors.

The readings are **system-wide snapshots**, not app-attributed VRAM
measurements or a proof of successful GPU-memory release. GeForce/Windows
WDDM may provide N/A metrics; such failures are reported as inconclusive.
CI has synthetic readings only; it never runs the owner's GPU.

See [M3-18 owner-run NVIDIA VRAM observation](docs/M3_OWNER_VRAM_OBSERVATION.md).

## Shared GPU safety lockout after unverified CUDA process cleanup (M3-17)

The Tauri DEBUG-only runtime now remembers a failed Windows Job
Object cleanup check **regardless of whether it occurred in image
generation or in a read-only CUDA/VRAM diagnostic**. The shared
fail-closed safety latch prevents new GPU diagnostics and new inference
jobs until the application restarts, rather than treating a diagnostic
cleanup failure as a transient read-only error.

A failed CUDA probe's process-group termination is verified on normal
exit, timeout, missing stdout, and process-status read errors. Even if
later code reports a successful cleanup, it cannot clear an already-set
fault within the same process. The user is asked to inspect remaining
Python processes in Task Manager before restarting; no automatic retry
or GPU memory-reset command is introduced.

See [M3-17 shared cleanup fault latch](docs/M3_SHARED_CLEANUP_FAULT_LATCH.md).
GitHub CI verifies synthetic logic and Windows process groups only,
not CUDA memory reclamation on the actual RTX 2060 SUPER.

## Verify all Windows job processes are gone after GPU work (M3-16)

The DEBUG-only SDXL runner now checks `QueryInformationJobObject`
accounting after Windows Job Object termination. A completed job is
only considered cleaned up when `ActiveProcesses == 0`, with a
bounded two-second verification check. Otherwise the job reports
`process_cleanup_failed` even if the parent Python interpreter has
exited or a cancellation/timeout was requested. The read-only CUDA
diagnostic uses the same cleanup verification after its successful
probe. Existing safeguards, private stdin, fixed offline processes,
and conservative RTX 8GB memory policy remain.

This proves **no processes remain associated with that Windows Job
Object**, not that CUDA reclaimed all VRAM. Real RTX 2060 SUPER SDXL,
GUI cancellation and system-wide GPU observation are still untested.

See [M3-16 verified Windows process cleanup](docs/M3_VERIFIED_PROCESS_CLEANUP.md).

## Keep private generation prompts off process command lines (M3-15)

Windows Tauri DEBUG builds now send image generation settings to the
fixed offline Python script through a **bounded 32KiB UTF-8 JSON stdin
pipe**, not `--prompt` and `--checkpoint` process arguments. This
reduces accidental command-line disclosure and supports Unicode prompts
that begin with a dash. Python strictly validates the schema, rejects
duplicate/unknown keys and non-standard numbers, and requires explicit
`--request-stdin --execute --metrics` mode flags.

The Windows job supervisor, CPU-offloading SDXL engine, explicit user
consent, fixed local interpreter/script, 30-minute Job Object watchdog
and verified PNG result remain. No automatic retry, download, network
execution, release-mode GPU access or real hardware QA is introduced.
Manual Python CLI flags remain available for deliberate terminal use.

See [M3-15 private stdin protocol](docs/M3_PRIVATE_GENERATION_STDIN.md).

## GPU generation failure classification and safe recovery (M3-14)

The Windows Tauri DEBUG-only job supervisor reports an allowlisted,
non-sensitive `failure_code` alongside its existing terminal job phase.
Codes cover CUDA out-of-memory, missing Python inference dependency,
CUDA runtime failure, unsuccessful inference, Windows process cleanup
failure, PNG verification failure, timeout and explicit cancellation.
Raw model paths and stderr are **not** exported.

The image workspace renders Korean, category-specific help. For GPU OOM
or timeout it offers a voluntary 512×512/15-step settings shortcut,
which resets previous user consent and **never** automatically reruns
a GPU job. Actual generation still requires independent consent and a
fresh VRAM check. CUDA cache/driver cleanup and image quality remain
unverified on the user's real 8GB device.

See [M3-14 GPU job recovery](docs/M3_GENERATION_FAILURE_RECOVERY.md).

## Inspect VRAM before generation and recover safely (M3-13)

The Windows Tauri DEBUG image workspace now offers a separate
**VRAM 재검사** control for the currently selected width and height.
The read-only native command `check_local_generation_vram` takes only
image dimensions and uses the already-restricted local CUDA diagnostic
with a Windows Job Object, bounded output, and time limit. It returns
the conservative policy status, recognized reason codes, and a safe
initial 512×512/15-step suggestion. **No model is loaded and no image
is generated by the inspection.**

The UI explains low free/total memory and high 8GiB-card resolution,
offers a one-click 512×512 setting change and resets user generation/risk
consent on changing settings. Report state is invalidated whenever
the selected dimensions change. A positive status is merely an
instantaneous *preliminary* measurement: Rust always runs a **fresh,
independent** preflight immediately before real inference. Browser and
release execution remains disabled.

See [M3-13 VRAM recovery details](docs/M3_VRAM_PREFLIGHT_RECOVERY.md).

## Native desktop GPU VRAM safety check (M3-12)

Windows Tauri DEBUG generation now performs a **fresh local CUDA memory
probe before launching the SDXL model process**, using the same fixed
Windows Job Object supervised Python diagnostic as the existing GPU
status panel. A shared single-flight reservation prevents generation
or other diagnostics from racing while memory is inspected.

The same cautious 6 GiB total, 4 GiB free and 768×768 on <= 8 GiB GPU
criteria from M3-11 are enforced **inside Rust**, not just displayed
in the frontend. A separate unchecked VRAM-risk consent can permit
an explicit attempt that violates a heuristic threshold, but cannot
override missing CUDA, bad device readings or the normal user consent
requirement. Browser and release GPU execution remain unavailable.
This check is not a guarantee that the checkpoint will fit in VRAM.

See [M3-12 Tauri VRAM safety documentation](docs/M3_TAURI_VRAM_GATE.md).

## 8GB GPU VRAM safety gate (M3-11)

The owner-run hardware acceptance CLI checks total/free CUDA VRAM before
model loading. With less than 6 GiB total, less than 4 GiB free, or an
over-768×768 trial on a GPU with at most 8 GiB total, execution is blocked
until the user **explicitly** adds --acknowledge-vram-risk in addition
to --execute --confirm-gpu. Missing CUDA or invalid device readings
remain blocked regardless.

These values are cautious initial screening rules, **not** certified
requirements or proof that SDXL generation will succeed. Existing Tauri
DEBUG generation has separate controls and is not changed by this feature.
No real RTX 2060 SUPER hardware QA has been performed in GitHub CI.

See [M3-11 VRAM safety guide](docs/M3_VRAM_SAFETY_GATE.md).

## Target-device acceptance reporting (M3-10)

The repository includes `backend/hardware_acceptance.py`, an offline
owner-operated QA command. **Default invocation inspects SDXL metadata and
offline configuration only: it does not import Torch or start CUDA**.

```powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors"
```

Add `--inspect-gpu` for local CUDA device information (may initialize
CUDA, no model load). To attempt **real generation on your own PC**, supply
a prompt and both `--execute --confirm-gpu` plus low-memory settings.
The tool performs independent saved-image decoding and SHA-256 reporting,
but does not grade artistic quality or total GPU VRAM. Its structured
report excludes prompts and absolute local paths.

See [M3-10 target hardware acceptance guide](docs/M3_HARDWARE_ACCEPTANCE_CLI.md).
GitHub CI uses only injected synthetic models/GPU objects and does not
execute RTX 2060 SUPER inference.

## Verified local generation results (M3-8)

Windows Tauri **debug** generation now requests explicit CLI `--execute
--metrics`, collects bounded JSON output and validates the reported PNG
against the fixed local `outputs/` directory. Only the file name,
independently checked SHA-256, seed, generation-call time and optional
PyTorch CUDA allocator peaks are shown in the UI.

The M3-9 verifier additionally decodes PNG pixel data under resource limits
and matches the requested resolution; that proves a decodable image was saved,
**not** image quality, prompt fidelity or actual GPU compatibility. The UI clearly
marks unavailable memory metrics, and invalid CLI output is a failed job.
No generation API is exposed to browsers or Tauri release builds.

See [M3-8 generation verification guide](docs/M3_VERIFIED_GENERATION_METRICS.md) and
[M3-9 PNG structural QA](docs/M3_PNG_STRUCTURAL_QA.md).
Actual hardware validation remains pending.

## Desktop GPU readiness panel (M3-7)

The **이미지 생성** (Image Generation) workspace now includes a
**GPU 진단 실행** control for Windows Tauri debug builds. This invokes only
the fixed local `backend/gpu_diagnostics.py` inside the repository's
`.venv/Scripts/python.exe`, without a frontend-provided path or shell.

The 25-second bounded Windows Job Object command returns a validated,
size-limited report showing CUDA/PyTorch status and current VRAM. It is
disabled in browsers, release builds, and while image generation is active.
It cannot prove that an SDXL model will load or generate a valid image.

See [M3-7 desktop GPU diagnostics](docs/M3_DESKTOP_GPU_DIAGNOSTICS.md).

## GPU hardware readiness (M3-6)

To inspect a locally installed CUDA-capable PyTorch environment **without loading a
checkpoint or running diffusion**, execute:

```powershell
.\.venv\Scripts\python.exe backend\gpu_diagnostics.py
```

The JSON result identifies the PyTorch CUDA build, GPU name and VRAM total/free
at inspection. This can initialize a CUDA context, but it does not establish
SDXL compatibility or benchmark image quality. When explicitly generating a
real image via the CLI, add `--metrics` alongside `--execute` to print
elapsed time, observed torch CUDA allocator peaks, and the output PNG SHA-256.
These metrics are **not total VRAM use** and are not collected remotely.

See [M3 GPU hardware QA](docs/M3_GPU_HARDWARE_QA.md) for local test
acceptance criteria. CI uses only mocks; RTX 2060 SUPER real-device QA is pending.

## Experimental SDXL image generation (M3-1)

On a machine with CUDA-enabled PyTorch, additional optional dependencies,
an SDXL safetensors checkpoint and its offline pipeline configuration, run:

```powershell
python backend/generate_sdxl.py --checkpoint "checkpoints/model.safetensors" --prompt "An original watercolor landscape"
```

This is **dry run only**. To attempt one real local image, add `--execute`.
No model or config is downloaded automatically. Only checkpoint files under
the repository's `models/checkpoints` root are accepted. Images, if
successfully generated, go to `outputs/` and do not overwrite existing files.

See [M3 local inference setup, limits and GPU QA](docs/M3_LOCAL_INFERENCE.md).
This CLI is not yet connected to the web/Tauri UI.

## Development quick start

Prerequisites: Python 3.12+, Node.js 22+, and Rust/Windows C++ Build Tools +
WebView2 when developing the Tauri desktop shell.

In terminal A:

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

In terminal B (repository root):

```powershell
npm install
npm run dev
```

Optional Tauri desktop dev window after Rust setup: `npm run tauri dev`.
The FastAPI backend is **not bundled or auto-started yet**.

## Local file import

In the `backend` folder, using a Python desktop installation with Tkinter:

```powershell
python model_import.py --category checkpoints
python model_import.py --category loras --source "C:\Downloads\lora.safetensors"
python model_import.py --category checkpoints --verify "checkpoints/my-model.safetensors"
```

Accepted categories: `checkpoints`, `loras`, `vae`.
The CLI chooser is independent from the newer **Tauri-native model import button**.
During Tauri development both use the repository \`models\` directory.
Release builds import and browse from the same app-local-data \`models\` directory
using Tauri. Python API auto-start, model inference, and packaged backend integration
are not implemented yet.
Safetensors only; legacy CKPT is deliberately never imported or loaded.
Model files and local integrity registries are ignored by Git.

## Docs and verification

- [M2 model catalog, metadata, import and integrity](docs/M2_MODEL_CATALOG.md)
- [M3 offline SDXL CLI and hardware-validation guide](docs/M3_LOCAL_INFERENCE.md)
- [M3-6 CUDA readiness and target hardware QA](docs/M3_GPU_HARDWARE_QA.md)
- [M1 developer environment](docs/DEVELOPMENT.md)
- Backend tests: `cd backend && python -m pytest -q`
- Frontend: `npm run build && npm test`
- GitHub: `.github/workflows/ci.yml`

M10 is reserved for a Krea-inspired canvas/editor workflow, **not** multi-character
generation. ComfyUI remains an optional future engine adapter.

- [M3-8 generation metrics, checksum and Windows debug limitations](docs/M3_VERIFIED_GENERATION_METRICS.md)
