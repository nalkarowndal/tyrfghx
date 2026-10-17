# M3-6 — CUDA hardware readiness and real-device QA

M3-6 adds **opt-in hardware inspection** and **measurement hooks** to support
the RTX 2060 SUPER 8 GB acceptance workflow. These are not proof of successful
image generation and are NOT collected remotely.

## 1. Local CUDA readiness check

After following [M3-1 setup](M3_LOCAL_INFERENCE.md) to install a CUDA-enabled
PyTorch wheel into `.venv`, run from the repository root:

```powershell
.\.venv\Scripts\python.exe backend\gpu_diagnostics.py
```

The tool prints a schema-v1 JSON report containing:
- Python host operating system (no hostname, account or home folder)
- PyTorch version and CUDA build version
- CUDA device index, GPU name, compute capability
- GPU total VRAM and free VRAM at the moment of inspection
- Initial suggested 512 × 512, 15-step, single-image, CPU-offload trial

If Torch is missing, CPU-only or cannot use CUDA, an actionable status is
printed without a traceback or filesystem paths. The default invocation
returns success even for an informational failure state; for a CI-style check
that must exit nonzero when CUDA is not detected, use `--strict`.

This tool does not download models, run diffusion, create an image, test
checkpoint or LoRA compatibility, or promise a speed/quality outcome. It
**may initialize CUDA** while obtaining driver/device information.

## 2. Actual local SDXL single-image trial (user machine only)

Place a legally usable SDXL safetensors model in the existing safe catalog
and prepare local `models/configs/sdxl-base-1.0` files. Check
`docs/M3_LOCAL_INFERENCE.md` for all prerequisites.

First run a dry preflight (no model load):

```powershell
.\.venv\Scripts\python.exe backend\generate_sdxl.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --prompt "An original watercolor landscape"
```

Only when GPU support and configuration are ready, explicitly run:

```powershell
.\.venv\Scripts\python.exe backend\generate_sdxl.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --prompt "An original watercolor landscape" --width 512 --height 512 --steps 15 --seed 42 --execute --metrics
```

The opt-in `--metrics` flag requires `--execute`. After **successful**
inference it adds an `elapsed_seconds` measurement, PNG SHA-256, and
PyTorch peak allocated/reserved bytes where supported to the JSON result
printed on the terminal. It does not create automatic telemetry uploads.

Important: CUDA allocator peak **excludes GPU allocations held by the driver
and other processes** and does not equal total GPU VRAM consumed. The elapsed
time includes model loading and execution in the Python CLI, but not OS
startup time. GPU peak statistics may be unavailable even when an image
was saved; this does not invalidate a successfully written PNG.

## 3. Manual quality and resource acceptance report

Use the following checklist on the actual target Windows PC. Mark items
`passed`, `failed`, or `not tested`. Do not label these as passed from
GitHub Actions alone.

| Test | Required observation |
| --- | --- |
| GPU recognition | PyTorch CUDA build, GPU name, VRAM total/free |
| SDXL compatibility | A real authorized checkpoint loads with offline config |
| First generation | PNG opens, output SHA-256 recorded |
| Quality | Visually inspect prompt adherence and common artifacts |
| Memory | Observe Task Manager/nvidia-smi VRAM alongside allocator peaks |
| Cancellation | Start a job and cancel; verify no lingering Python children |
| Watchdog | Confirm behavior for timeouts using a safe reduced-time test fixture |
| Offline operation | Disable network and confirm local resources are sufficient |
| Failure paths | Remove model config, simulate CUDA OOM, verify actionable errors |
| Repeatability | Reuse fixed seed/settings and note whether outputs vary |

Keep sensitive paths, prompts and image data private when sharing logs.
For support, only the hardware readiness JSON, package versions, sanitized
error category, and image checksum should be needed initially.

## 4. Automated QA boundaries

`backend/test_gpu_diagnostics.py` uses mock PyTorch/CUDA implementations.
The added `backend/test_generation.py` tests use a fake CUDA allocator
and synthetic saved PNG bytes. Neither test suite loads actual torch weights,
initializes a real GPU or benchmarks an 8 GB card in GitHub CI.

Existing Windows Rust Job Object tests remain in the stacked M3-5 PR.
Actual Windows GUI, model weight compatibility and VRAM reclaim on the target
device are still open acceptance work.

Official API references:

- [PyTorch CUDA API](https://docs.pytorch.org/docs/stable/cuda.html)
- [PyTorch CUDA memory API](https://docs.pytorch.org/docs/stable/generated/torch.cuda.mem_get_info.html)
- [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)

## M3-7: GPU diagnostics directly in the Tauri application

In a Windows Tauri **debug development** build, open **이미지 생성** and
select **GPU 진단 실행**. The native IPC command `inspect_local_gpu` runs
only the fixed `backend/gpu_diagnostics.py` via the fixed local
`.venv/Scripts/python.exe` and returns the same versioned JSON report to
the interface. This check does not download any model or start diffusion.

The command is disabled in browser/release mode, while a generation process
is active, and if the local environment is missing. It uses a 25-second
timeout, a bounded JSON response and a Windows Job Object.

This is a convenience over running the Python diagnostic manually, not
actual GPU image generation, actual peak VRAM benchmark, or comprehensive
device compatibility certification. Windows interactive QA remains pending.

See [M3-7 details](M3_DESKTOP_GPU_DIAGNOSTICS.md).
