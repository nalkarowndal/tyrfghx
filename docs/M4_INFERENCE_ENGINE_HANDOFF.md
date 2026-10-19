# M4 handoff — aiimage inference engine integration (post M3-Final)

**This document authorizes no GPU action, downloads, model file access,
production release change, or merge.** It preserves the proven M3
Windows shell/authentication/installer/data-safety baseline and
defines the next scope once the owner approves M3 closure.

## What M3 provides

- Windows Tauri 2 + React 19 app, native local model catalog with
  SHA-256 verification, consent-oriented controls and fail-closed
  native release GPU policy.
- Packaged **read-only** FastAPI service, with process ownership,
  authenticated loopback APIs, UI health/restart, hashed Windows
  backend dependencies and safe uninstall data handling.
- Opt-in Windows CI: repeatable NSIS installation/repair,
  two-version metadata upgrade and downgrade rejection,
  early pre-install failure/retry and real installed backend GUI QA.
- Authenticated metadata-only inventory for fixed AI dependencies,
  with truthful `not_verified` and a static recommendation to
  use a separate inference worker/virtual environment.

No real RTX 2060 SUPER GPU, CUDA kernels, model loading, SDXL image
generation, video generation or LoRA inference was verified by M3.

## M4-1 — Separate inference worker and opt-in environment (CPU-only build QA)

1. Design worker authentication and a minimum local IPC contract
   independent of the read-only packaged FastAPI process. Preserve
   native-only binding and owned process lifecycles.
2. Define an isolated **user-selected** Python virtual environment
   location and a separate installer transaction plan; enumerate
   storage budget, metadata manifest, package pins and hashes.
   Never install into the frozen read-only backend's environment.
3. Document Windows PyTorch/CUDA build candidate selection from
   official compatibility references and runtime detection, not from
   a guessed `+cu###` suffix or GPU name alone.
4. Implement *read-only, no-GPU, no-download* version checks and
   expected-disk-usage preview with tests for malformed wheels,
   permission errors, cancellation and path traversal.
5. Ask explicit owner approval before pip installs, large downloads,
   device diagnostics or touching private model files.

## M4-2 — Explicit owner-approved RTX 2060 SUPER 8GB validation

Only when a compatible local Windows GPU environment is provided
and the user specifically authorizes this step:

- Report exact GPU name, driver, CUDA runtime, free/total VRAM, and
  Torch wheel build **from an explicitly consented device probe**.
- Validate one small known-safe model/load plan within 8GB VRAM,
  timeouts, memory limits, job-tree cleanup and forced-stop handling.
- Then validate one SDXL still image against output-format
  and file integrity checks and record peak VRAM/time.
- Stop on driver mismatch, OOM, unsafe download/unsigned dependency,
  user cancellation or leaked process; do not promise successful
  generation on the basis of metadata alone.

## M4-3 — Advanced image features

Independent checkpoints, model source/manifests and license review;
Anima/Illustrious, prompt editor, LoRA compatibility and multi-character
identity separation. Every separate model/LoRA pipeline needs
correctness, privacy, memory and artifact provenance tests.

## M4-4 — Video and optional ComfyUI integration

Separate process/port, nodes and package provenance, explicit
memory/disk/VRAM budgets, cancellation, isolation and a quality
evaluation plan. Video model integration cannot be declared done
from UI mockups or mocked W3C interactions.

## M4 acceptance gates

- New M4 Draft PRs stacked from the **verified, explicitly approved**
  integration base (not from stale `main`).
- Unit, integration and actual Windows non-GPU UI QA green at each
  step; feature flags isolate unfinished GPU tasks from release builds.
- Explicit consent, artifact checksums, no secret leakage in prompts/
  process args or logs, reliable cancel/cleanup on Windows.
- Evidence-backed report with clear distinction: design,
  implementation, CPU QA, real GPU verification, released product.

## Blockers inherited from M3

- Long Draft PR stack not integrated to `main`, requiring review.
- Production CSP configuration and signed installer/clean-machine
  distribution QA not completed.
- Schema data migration and mid-write installer rollback unknown.
- Driver/VRAM/device capability unknown; GPU tests not run.

**Next recommended action:** complete [M3-Final acceptance](M3_FINAL_ACCEPTANCE.md),
then open an **M4-1 design/CPU-only integration Draft PR** that implements
only separately reviewable host/worker protocol and installer
manifest planning. Do not add an M3-47 milestone.
