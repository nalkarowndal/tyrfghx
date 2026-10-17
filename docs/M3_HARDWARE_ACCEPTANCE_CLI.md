# M3-10 — Owner-run RTX 2060 SUPER hardware acceptance report

This milestone adds a **local, explicit SDXL validation workflow** in
`backend/hardware_acceptance.py`. It is an acceptance helper, not an
autonomous GPU benchmark, model downloader, or deployment of the Windows app.

GitHub CI does not have the owner's RTX 2060 SUPER or SDXL model weights.
Its tests inject fake CUDA, fake PNG files, and fake inference callbacks.
**Only an explicit run on the owner's PC can produce actual hardware results.**

## Preparation on the target Windows PC

1. Checkout `feat/m3-hardware-acceptance-cli` and keep the repository-local
   Python environment at `.venv/Scripts/python.exe`.
2. Install CUDA-enabled PyTorch from the [official selector](https://pytorch.org/get-started/locally/)
   and the optional `backend/requirements-inference.txt` dependencies into that environment.
3. Prepare an authorized SDXL safetensors checkpoint in
   `models/checkpoints/`, registered as an SDXL-family model in the catalog.
4. Prepare the complete **offline** SDXL config under
   `models/configs/sdxl-base-1.0`, including `model_index.json`.
   Neither the QA tool nor the engine downloads missing components.

### Step A: Safe metadata preflight (no Torch or GPU)

From the repo root:

```powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors"
```

Outputs schema-v1 JSON with `preflight_ready_gpu_unchecked` or a blocked
preflight status, and manual checks marked `not_tested`. This default
mode does **not** import Torch, start CUDA, load weights, or generate PNGs.

### Step B: Optional GPU probe (no model load)

```powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --inspect-gpu
```

Outputs `gpu_probe_only` plus the local PyTorch/CUDA and VRAM status.
This **may initialize CUDA** to query the device, but cannot prove that
SDXL inference will fit in the available 8GB VRAM. Failure to read
CUDA should not crash or expose local filesystem paths.

### Step C: Explicit 512×512 single-image attempt

Only when you have model rights, a working CUDA environment, adequate
disk space, and consent to a potentially slow / memory-heavy test:

```powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --prompt "An original, quiet watercolor landscape" --width 512 --height 512 --steps 15 --seed 42 --execute --confirm-gpu
```

**Both** `--execute` and `--confirm-gpu` are required. The command
enforces the original `GenerationSettings`, safetensors header checks,
SDXL-family metadata preflight and local config checks before trying
Diffusers inference with CPU offloading. It uses only already-installed
local resources.

After the actual inference call, Pillow must successfully verify the PNG
and decompress its pixels, with matching expected dimensions, fixed
`outputs/` storage, strict `aiimage-<uuid>.png` naming and the same 8MiB
size cap used by Tauri. The tool computes a SHA-256 and optionally reports
PyTorch CUDA allocator peak allocated/reserved bytes and elapsed time.

The JSON report deliberately omits prompts, model absolute paths, raw
tracebacks, user names, environment variables, access tokens, and full
output paths. Failures are classified into static categories such as
`cuda_out_of_memory` or `missing_inference_dependency`.

## How to interpret results

- `preflight_ready_gpu_unchecked`: Metadata/config present, **GPU untested**.
- `gpu_probe_only`: PyTorch CUDA was inspected; **no model weights loaded**.
- `gpu_not_ready`: CUDA driver / PyTorch cannot be used for the attempted run.
- `generated_png_decoded`: User explicitly executed the local Python
  inference flow and the saved PNG was decoded and hashed. **Not** a visual
  quality grade or proof of model provenance.
- `generation_failed`: A sanitized failure category is included; no
  sensitive exception text.
- `manual_checks`: Visual prompt adherence, **total** GPU VRAM peak,
  GUI behavior, offline packet observation and Windows process-tree
  cleanup remain `not_tested` until reviewed by a human on the target PC.

The reported allocator peak counts memory managed by PyTorch; it excludes
other GPU applications, driver allocations and certain non-PyTorch
components. Use Windows Task Manager or `nvidia-smi` independently.

## Safety and resource caveats

**The acceptance CLI performs synchronous inference** if both opt-in flags
are supplied. Unlike the Windows Tauri dev-only Job Object launcher, this
standalone Python command does not implement a 30-minute OS watchdog or
guarantee process-tree cancellation. To specifically test cancellation,
use the Tauri development UI and inspect remaining processes manually.
Do not interpret its success as complete app/GUI acceptance.

This milestone does NOT add a generic file-picker path, unauthenticated
HTTP execution API, data uploads, model downloads, release-mode GPU
execution, LoRA/Anima support or production Windows packaging.

## CI verification

`backend/test_hardware_acceptance.py` confirms that default preflight
never imports GPU libraries, a missing config prevents inference, the
double consent gate cannot be bypassed, CUDA failures block execution,
CUDA OOM paths are sanitized and the JSON report hides prompt and
absolute paths. All inference tests are deterministic CPU-only fakes.
The existing Windows Rust, frontend and Python CI suites still run.

References: [PyTorch CUDA memory](https://docs.pytorch.org/docs/stable/torch_cuda_memory.html),
[SDXL local setup](M3_LOCAL_INFERENCE.md),
[M3-9 PNG validation](M3_PNG_STRUCTURAL_QA.md).
