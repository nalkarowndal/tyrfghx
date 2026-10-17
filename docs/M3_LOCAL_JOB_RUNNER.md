# M3-3 — Windows development-only local GPU job supervisor

M3-3 adds a **user-initiated, single-job launcher** to the Tauri Image
Generation screen. This is a developer preview, NOT a packaged inference
service or evidence that the RTX 2060 SUPER 8 GB has generated an image.

## Explicit enablement and isolation

The Rust command `local_generation_supported` is TRUE only in **Windows
Tauri debug builds**. In release builds (or other OSes), the capability is
disabled at the Rust boundary, regardless of frontend state.

Only the following hardcoded executable and script may run:

- Interpreter: `<repo>/.venv/Scripts/python.exe`
- Script: `<repo>/backend/generate_sdxl.py`
- Fixed working directory: repository root
- Fixed model root: `<repo>/models`; output root: `<repo>/outputs`

The frontend cannot supply an interpreter, executable, script path, output
path, URL, working directory, or shell command. Rust uses `std::process::Command`
with a hardcoded argv format, **never** `cmd.exe`, `powershell.exe` or a shell
plugin with general command permissions. The Python script gets `--execute`
only after an explicit checked consent box.

User-supplied model IDs are limited to direct
`checkpoints/<name>.safetensors` entries. Rust independently validates
format, family metadata hints, known root, and the presence of local SDXL
configuration files. Parameters are bounded and validated again in Python.
No network downloads are initiated by the runner. It sets `HF_HUB_OFFLINE=1`
and uses M3-1 Diffusers `local_files_only=True`. A family metadata match
does NOT guarantee usable tensors, model license or 8GB memory fit.

## Preparing your own Windows development environment

In the repository directory, use Python 3.12 to create a virtualenv in the
EXACT fixed path:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Install a CUDA-enabled PyTorch wheel from the official selector:
https://pytorch.org/get-started/locally/ . Use that `.venv` interpreter.
Install the optional runtime dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-inference.txt
.\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available())"
```

CUDA must report True for real GPU inference. Add a legal SDXL safetensors
checkpoint and independently provision the local SDXL Diffusers config tree in
`models/configs/sdxl-base-1.0`. These are NOT downloaded automatically.

Start `npm run tauri dev`, select the checkpoint, enter prompt and bounded
generation parameters, check the explicit GPU consent box and press
**GPU 생성 시작 (개발판 전용)**.

### Job states

- `idle`: no job started since app launch
- `running`: Python child started; **not** diffusion-step progress
- `cancelling`: process termination requested; not yet confirmed
- `succeeded`: Python child exited with code zero. Does not attest image
  quality, prompt compliance, GPU performance, or even gallery readability.
- `failed`: Python child failed. Known CUDA memory/module errors are
  summarized without exposing arbitrary log content in the UI.
- `cancelled`: the termination request was observed and the child ended

At most one job may run at once. The frontend polls status approximately every
1.5 seconds while a job is running/cancelling, but there is NO percentage
progress and no automatic retry. You can manually refresh the result gallery.
The Rust process manager attempts to kill an active child when it drops.

**Cancellation caveat:** Windows `Child::kill` terminates the immediate
Python process, not a guaranteed entire process tree. It may not terminate
worker descendants started by external libraries. Process-tree supervision,
robust graceful shutdown and recovery after OS crash remain future work.

## Security boundaries and known limitations

- Browser mode and Tauri release builds **cannot start** GPU jobs.
- Unauthenticated FastAPI endpoints still do NOT execute model inference.
- Rust never launches a frontend-specified binary or arbitrary path.
- No automatic Python installation, Python sidecar packaging, model download,
  dependency installation, version negotiation or code signing.
- Only recorded checkpoints of the SDXL family are considered, including
  unverified user metadata hints; loading is still unverified.
- No GPU-validated performance; no LoRA/Anima/Illustrious runtime support yet.
- No CUDA step-level progress. Exit code + bounded diagnostic classification
  are not detailed model execution telemetry.

## CI and manual acceptance criteria

GitHub Actions compiles/tests Rust on Windows, runs Vitest/build on the
frontend, and runs Python tests on Windows and Linux. The Rust tests cover
parameter validation, explicit consent, error categorization, bounded stderr,
and refusal to run without local dependencies. Frontend tests cover the IPC
argument shape and desktop guard. CI does NOT download weights or execute GPU
inference.

Manual Windows acceptance for M3-3 should include:
1. With no `.venv`, clicking start yields an actionable error and no child.
2. With working dependencies, only one child can run; second start is rejected.
3. Cancel a live generation and observe a terminal state.
4. Simulate an OOM and verify a clear low-VRAM suggestion.
5. Verify no automatic downloads/network traffic, no output overwrite,
   and actual PNG readability in the gallery.
6. Record model name/source/license, driver and PyTorch versions, GPU
   model/VRAM, measured runtime/peak VRAM and exact output checksum.

DO NOT mark live image generation as device-tested until these tests pass.

## M3-4 — bounded job lifetime and diagnostic collection

The Windows debug-only runner now enforces a **30-minute wall-clock
timeout** per job (1800 seconds), providing status fields
`elapsed_seconds` and `time_limit_seconds`. These describe wall-clock
time, **not** diffusion-step progress or a completion percentage.
The UI displays both values, and a successfully exited job causes a
read-only gallery refresh.

On timeout Rust attempts to terminate the immediate Python child, reports
`cancelling` while termination is pending, then reports `timed_out`
once the child exits. The previous stderr-draining thread is intentionally
**not joined** in the job-monitor thread; a descendant inheriting the pipe
can no longer indefinitely prevent the runner from returning a terminal
status after the direct Python child has exited. Diagnostic data in shared
memory is limited to the most recent 8192 bytes and is only used to map
known failures to short Korean UI messages.

Safety caveats: Windows `Child::kill` affects only the immediate child and
is not complete process-tree isolation. On process termination failure the
job may remain in cancelling until it exits. A process-tree/Job Object
implementation and a target-device test are required before shipping a
production runner. The 30-minute watchdog itself does not guarantee all
descendants have stopped or GPU memory has been released. No model, CUDA
GPU or inference process is run in CI.

## M3-5 process-group supervision update

The earlier `Child::kill` limitation is now mitigated for normal Windows
subprocess inheritance using a Win32 **Job Object**. The launcher creates
Python suspended, assigns it to a group configured with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, then resumes it. Job setup failure
**fails closed**, with no ungrouped fallback. Explicit cancel, watchdog
expiry, post-child-exit cleanup and app shutdown attempt to terminate the
whole job. See [M3-5 technical documentation](M3_WINDOWS_PROCESS_GROUP.md).

This still does not cover all possible process-spawning mechanisms, does not
guarantee OS/GPU driver VRAM reclamation, and is not a real RTX 2060 SUPER
hardware acceptance test. The production executable remains blocked from
starting GPU jobs.
