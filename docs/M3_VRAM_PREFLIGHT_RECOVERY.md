# M3-13 — read-only desktop VRAM preflight and guided recovery

M3-13 gives the Windows Tauri DEBUG image generation workspace an
explicit, safe inspection and recovery flow **before** the user attempts
a CUDA model execution. It builds on M3-12's native VRAM execution gate.

## User flow

1. Choose an SDXL checkpoint, image width and height. The new **VRAM 재검사**
   button runs the fixed read-only native `check_local_generation_vram`.
2. Rust accepts only requested width and height (512 to 1024 inclusive,
   multiples of 64). No checkpoint ID, Python executable, shell command,
   prompt, output directory or user-provided path can be passed to this
   command. Browser and release builds fail closed.
3. The command holds the shared single-flight GPU diagnostic reservation
   while a background worker invokes the existing strictly bounded
   local `backend/gpu_diagnostics.py` in a Windows Job Object.
   Timeout is 25 seconds, and the process must report valid versioned
   CUDA device diagnostics before memory is evaluated.
4. Rust computes the same native M3-12 safety policy used at actual
   generation start. The response is a small allowlisted struct containing
   `trial_allowed` or `blocked_by_default`, static reason codes, total
   and momentarily free VRAM, dimensions, and suggested 512×512/15-step
   trial settings. No private paths or raw stderr/stdout are returned.
5. UI renders explanatory Korean messages. Reasons cover under-6GiB
   total VRAM, under-4GiB free VRAM, or pixel area exceeding 768×768
   on a device with at most 8GiB total VRAM.
6. On a blocked result, the user can close other GPU-consuming
   applications and click **VRAM 재검사** again. If dimensions are larger
   than 512×512, **권장 512×512 설정 적용** changes both dimensions
   and reduces the step count to 15; it does NOT implicitly retry
   inference.
7. Both regular GPU execution consent and the separate VRAM-risk
   acknowledgement are reset when safe settings are applied. The preview
   report is also reset when image dimensions change.
8. A positive read-only result is **not authorization** to execute.
   On actual GPU generation, the existing Rust M3-12 launcher runs
   another fresh CUDA probe, checks the safety policy independently,
   requires ordinary user consent, and uses a supervised child with
   30-minute timeout and process group termination.

## Why snapshot results must not be cached as permissions

A PyTorch CUDA free-VRAM snapshot can become stale immediately when
another process allocates GPU memory. The UI deliberately labels results
as momentary preliminary checks and never supplies reported memory
values to the generation command. The generation command re-reads the
local GPU itself before launching the diffusion model.

If CUDA/PyTorch is unavailable, the inspection fails with an actionable
environment error, NOT a green compatibility claim. Even a passing
probe can still encounter CUDA OOM during model loading or generation.

## Automated test coverage and limits

- Rust tests verify low free and total memory, high 8GiB-card pixel area,
  allowed conservative trials, rejected invalid memory or dimensions,
  safe reason-code serialization, and IPC rejection of arbitrary
  executable/model fields.
- Vitest checks fixed command invocation with width/height only,
  browser execution blocking, disallowed dimensions and reason labels.
- Existing Python Linux/Windows and Windows Rust CI still run.

GitHub CI uses CPU-only synthetic tests: **no real RTX 2060 SUPER SDXL
image, actual system-wide peak VRAM observation, Windows GUI interaction
or process-tree cancellation is verified**. Manual hardware acceptance
must still be performed on the user's machine, using the
M3_HARDWARE_ACCEPTANCE_CLI.md workflow.

References:
- https://v2.tauri.app/develop/calling-rust/
- https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- M3_TAURI_VRAM_GATE.md
