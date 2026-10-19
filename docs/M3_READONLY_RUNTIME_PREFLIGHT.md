# M3-45 — Read-only AI runtime dependency inventory (no GPU or model imports)

## Goal and verified baseline

M3-44 [general CI #39183632358](https://github.com/nalkarowndal/tyrfghx/actions/runs/39183632358)
passed **4/4 jobs**. [Actual hosted Windows install QA #39183584758](https://github.com/nalkarowndal/tyrfghx/actions/runs/39183584758)
also completed successfully, including early pre-install abort with exit code
83, unchanged installed app/backend/user files, clean same-version retry,
post-retry GUI backend restart and synthetic model/output preservation.

That completes a bounded installer-safety baseline; it does **not** certify
mid-write transactional rollback, production signing or GPU inference.

M3-45 starts the next product-facing milestone: report which **optional**
image-inference Python dependency *distribution metadata* is visible to
the running Python API, while always honestly reporting **not verified**
for device/CUDA/model execution readiness. Installed package metadata
is not evidence of usable GPU kernels, CUDA driver, appropriate VRAM
or safe checkpoint compatibility.

## Implementation

- New `backend/runtime_preflight.py` iterates a **fixed allow-list**:
  `torch`, `diffusers`, `transformers`, `accelerate`,
  `safetensors`, `Pillow`.
- Uses **only** `importlib.metadata.version`, never importing those
  modules, probing drivers, allocating VRAM, running subprocesses,
  downloading a package or opening user model files. No request can
  change the list or select an arbitrary filesystem path.
- For each distribution, emit `detected`, `missing` or `unknown`,
  with a bounded sanitized version or null. Metadata lookup errors
  are swallowed and marked `unknown`, not logged as local paths or
  treated as ready. No package name outside the allow-list is reported.
- The API's **existing** `GET /api/status` includes a
  `runtime_preflight` object. In packaged mode this endpoint already
  requires the Tauri native session's private Bearer token, rejects
  Origin headers and only serves loopback. Existing `engines`
  retain their truthful `unavailable` state.
- The React inspector displays the bounded inventory with an explicit
  Korean warning: this does not prove CUDA/GPU operation, model
  compatibility or successful image generation.
- No GPU generation/start buttons are enabled. Existing consent,
  snapshot integrity, VRAM safety checks and release-policy blocks are
  unchanged. No private file access or installation is introduced.

### Example non-readiness response

```json
{
  "schema_version": 1,
  "method": "distribution_metadata_only",
  "readiness": "not_verified",
  "cuda_tested": false,
  "gpu_accessed": false,
  "models_opened": false,
  "downloads_performed": false,
  "packages": [
    {"package": "torch", "state": "missing", "version": null}
  ]
}
```

(The actual response always includes all six allow-listed packages.)

## Verification

1. Deterministic Python unit tests use fake version metadata readers,
   covering all missing, all installed but still not verified, partial
   absence, dangerous/raw version values, unexpected lookup failures,
   and API's permanent non-readiness guarantees.
2. Linux and Windows Python CI each run normal `pytest`, without
   installing CUDA, weights or inference frameworks.
3. The original frontend CI builds the typed inspector and runs Vitest
   / Node WebDriver mock tests.
4. Windows locked Rust CI confirms the native app still compiles with
   production GPU policy unchanged.
5. On the opt-in GitHub Windows packaged-backend workflow, the **real
   frozen PyInstaller executable** must deny unauthenticated
   `/api/status`, allow the owned token, and report the no-GPU
   inventory while proceeding through installed NSIS/GUI/uninstall QA.

Successful tests prove only **package metadata inventory**, not model
loading, PyTorch CUDA usability, sufficient 8 GB VRAM, inference speed
or media output validation.

## Next logical milestones

- Separately design an opt-in, non-bundled runtime environment with
  pinned Windows CUDA/PyTorch wheels and disk usage limits.
- Define explicit user consent and safe GPU probe execution as a
  separate optional task; do not conflate installation with readiness.
- Only then, on an authorized compatible GPU, measure actual model
  loading, OOM handling and output correctness.
- Windows unsigned NSIS QA and signed/distributable installers also
  remain separate from the non-shipped runtime inventory.

Official references:
- https://docs.python.org/3/library/importlib.metadata.html
- https://docs.pytorch.org/get-started/locally/
- https://docs.pytorch.org/docs/stable/generated/torch.cuda.is_available.html
