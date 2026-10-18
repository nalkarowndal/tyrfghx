# M3-11: Conservative 8GB GPU VRAM safety gate

This milestone adds a pre-inference memory safety decision to the **standalone**
offline hardware acceptance Python CLI. The Windows Tauri DEBUG job runner
continues to have its own consent and Job Object controls and is unchanged.

## Heuristic thresholds (not certified hardware requirements)

| CUDA observation | Default policy |
| --- | --- |
| CUDA unavailable or nonsensical total/free measurements | Always block |
| GPU total VRAM under 6 GiB | Block until separate risk acknowledgement |
| GPU free VRAM under 4 GiB | Block until separate risk acknowledgement |
| VRAM at most 8 GiB and requested pixel area above 768×768 | Block until separate risk acknowledgement |
| Otherwise | Allow a trial, not guaranteed inference success |

This behavior targets a conservative initial SDXL trial on the
RTX 2060 SUPER 8GB. Point-in-time free VRAM changes, and other GPU
processes/driver allocations are not included in PyTorch allocator peaks.
These thresholds are implementation heuristics, not NVIDIA or PyTorch
certified minima.

The acceptance report includes a new memory_policy section with safe
static reason codes, suggested 512×512 resolution, 15 inference steps,
and whether the user acknowledged additional risk. It excludes prompts,
raw exception data, local file paths, and rejects path-like GPU names.

## Execution workflow on the user's Windows computer

1. Metadata preflight; no CUDA import or model inference:

~~~powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors"
~~~

2. Optional CUDA headroom probe (may initialize the driver, no model inference):

~~~powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --inspect-gpu
~~~

3. Explicit conservative generation attempt on the owner PC:

~~~powershell
.\.venv\Scripts\python.exe backend\hardware_acceptance.py --checkpoint "checkpoints/YOUR_MODEL.safetensors" --prompt "An original watercolor landscape" --width 512 --height 512 --steps 15 --execute --confirm-gpu
~~~

When blocked for memory reasons, close other GPU-heavy applications or
reduce dimensions. An owner who explicitly accepts the extra risk can
append --acknowledge-vram-risk to the third command.

The additional acknowledgement is rejected unless both --execute and
--confirm-gpu are also present. It NEVER overrides missing CUDA or an
invalid GPU telemetry report. It does not bypass registered SDXL checkpoint
and offline configuration checks. This tool never downloads a model.

## Meaning of report statuses

- vram_safety_blocked: GPU looked usable, but conservative memory policy
  prevented Torch model loading. Check memory_policy.reasons.
- allowed_with_acknowledged_risk: Additional user consent accepted; there
  remains a real risk of OOM, failure or very slow generation.
- conservative_trial_allowed: One quick memory observation passed; it
  does not imply a model can fit or render correctly.
- generated_png_decoded: The CLI attempted inference and saved a readable
  PNG with independently checked SHA-256. It still cannot grade artistic
  quality or whole-device GPU VRAM consumption.
- The manual_checks fields for visual quality, system-wide GPU peaks,
  network isolation and Windows process-tree cleanup remain not_tested.

## QA scope

GitHub CI tests use synthetic checkpoint headers and injected fake CUDA
data. Cases cover low free/total VRAM, high-resolution 8GB trials,
negative or inconsistent device readings, explicit opt-in, inability to
bypass missing CUDA, and rejection of path-like GPU labels. No authentic
image is generated, and real hardware acceptance is still outstanding.

PyTorch reference: https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
