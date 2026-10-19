# M3-46 — Isolated AI inference environment plan (metadata only)

## Prerequisite verification

M3-45 introduced a bounded, authenticated inventory of distribution
metadata exposed by the **read-only packaged FastAPI backend**. It
does not import Torch, test CUDA, install packages, load models or
start image generation. [Its ordinary CI run](https://github.com/nalkarowndal/tyrfghx/actions/runs/39184988321)
passed all four jobs; the separate frozen Windows packaged-API run
[39184951497](https://github.com/nalkarowndal/tyrfghx/actions/runs/39184951497)
must be checked for actual success independently.

## Key architectural correction

The Python interpreter that runs the packaged, read-only FastAPI
sidecar is **not an inference environment**. Even if metadata inspection
sees a `torch` distribution, this does not establish a separate user
inference runtime, or that this build was compiled for the actual GPU.
Conversely, missing Torch from the packaged server does **not** mean the
user's Windows system lacks PyTorch.

M3-46 records this distinction as a machine-readable contract:

- `inspection_scope=current_api_python_process_only`.
- `inference_runtime_connection=not_connected`. No inference
  environment is selected, scanned, imported or owned by this API.
- `recommended_isolation=separate_python_virtual_environment`.
  Python 3.12 is the planned first Windows profile, not a detected
  installation or forced user selection.
- `installation_mode=manual_only`; automated package installation,
  automatic downloads, GPU probes and model execution stay **disabled**.
- `torch_wheel_hint` has `unknown`, `cpu_wheel_metadata`, or
  `cuda_wheel_metadata` based solely on a safely bounded distribution
  version suffix like `+cpu` or `+cu129` in the current API process.
  The `hardware_compatibility_verified` flag is **always false**.
  This tag alone does not prove CUDA driver compatibility,
  architecture/kernel support, GPU memory sufficiency or inference.
- The existing `engines: unavailable` and top-level
  `readiness: not_verified` never transition to ready because of the
  planner or the presence of all dependency versions.

The authenticated `GET /api/status` adds this as
`runtime_preflight.setup_plan`. The React inspector shows Korean
explanations and fixed official documentation references, **without
executing installation commands or enabling generation**.

## Test boundary

The new pure Python `runtime_plan.py` never performs file I/O,
network I/O, package installs, subprocess execution, CUDA or module
imports. Its input is already sanitized and allow-listed package
metadata from M3-45. Unit tests cover CUDA-tagged, CPU-tagged,
unrecognized, missing and malicious metadata; they verify the
separate runtime stays unconnected and GPU compatibility is never
claimed.

The existing Windows packaged-backend CI now asserts a real frozen
backend returns the full opt-in setup contract over authenticated
loopback status, and refuses unauthenticated access. Existing Windows
NSIS upgrade, downgrade rejection, preinstall failure and retry,
real installed backend restart and uninstall user-data preservation
must continue passing. Normal CI still requires frontend,
Linux/Windows Python and locked Windows Rust success.

## Not implemented or verified

There is no installer for the separate inference runtime, no pinned
CUDA wheel download, no GPU probe, no user consent workflow for
actual inference, no model loading, no RTX 2060 SUPER benchmark
and no image output. A real 8 GB VRAM compatibility test requires a
subsequent *explicitly authorized* GPU-stage run with a selected
model and isolated device environment.

A true external runtime installation step will need a dedicated
user-controlled directory, downloadable wheel/lock verification,
staging and cancellation, per-device opt-in, Windows Job Object
cleanup, disk and VRAM limits, and rollback. Do not reuse the
packaged API's Python process as the inference worker.

Official references:
- [Python venv](https://docs.python.org/3/library/venv.html)
- [PyTorch Windows installer selection](https://pytorch.org/get-started/locally/)
- [PyTorch CUDA availability](https://docs.pytorch.org/docs/stable/generated/torch.cuda.is_available.html)
