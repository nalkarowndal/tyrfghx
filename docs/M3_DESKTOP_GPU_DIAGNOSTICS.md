# M3-7 — Windows Tauri GPU readiness panel

This milestone connects the existing M3-6 GPU readiness inspection to
the **이미지 생성** React/Tauri workspace.

## What it does

A user clicks **GPU 진단 실행** in the Windows Tauri DEBUG build.
A Rust command, `inspect_local_gpu`, starts the *fixed* local
`.venv/Scripts/python.exe backend/gpu_diagnostics.py`. It never accepts a
program, model, file path, URL, prompt, or arbitrary command from the webview.

The report shows the local Torch version, CUDA build, detected GPU name,
compute capability, momentary total/free device memory, and conservative
512×512 / 15-step / 1-image trial guidance.

The Python diagnostic **does not run diffusion or load model weights**.
It may initialize the CUDA driver while querying device information.

## Security and resource limits

- Windows Tauri **debug builds only**, matching the existing M3 job runner.
  Release builds and browsers cannot invoke the diagnostic at the Rust layer.
- No diagnostic starts when a local generation job is running/cancelling.
- The executable and script must be present in the repository local
  `.venv/Scripts` and `backend` directories. Symlinked path components
  for those directories are rejected.
- `std::process::Command`, not a shell plugin. Arguments are fixed; no
  frontend-supplied source file or executable path.
- The process starts suspended and is attached to an OS-managed Windows
  Job Object before it is resumed. It is terminated when the report is
  received or on timeout. Launch/setup failures fail closed.
- 25-second maximum, at most 16 KiB of stdout read, with a short bounded
  grace period for receiving complete JSON. All stderr is discarded.
- Rust decodes a version-1 JSON schema with bounded, allowlisted fields and
  rejects malformed/unknown data; raw CLI output cannot be injected into UI.
- The check does not upload GPU reports, download resources, send telemetry
  or grant a generic filesystem/browser permission.

## How to test on your PC

1. Ensure Python is installed at `<repo>/.venv/Scripts/python.exe`.
2. Install a matching CUDA-capable PyTorch build per the official selector:
   https://pytorch.org/get-started/locally/
3. Run `npm run tauri dev` on Windows and choose **이미지 생성**.
4. Click **GPU 진단 실행**. Verify the GPU name, CUDA build, and VRAM
   total/free displayed.
5. Test in the absence of Torch to see `torch_missing`.
6. Run a generation then verify the diagnostic button is disabled while
   the job is active.
7. Test the same browser build and Tauri release: diagnostics must be
   disabled, with no GPU process started.

## Automated checks and remaining uncertainty

Rust unit tests cover JSON schema parsing, oversized/unknown data rejection,
device-memory bounds, and missing fixed local Python environment. TypeScript
Vitest checks the no-argument IPC contract, browser rejection and truthful
status messaging.

**No actual RTX 2060 SUPER 8GB device was queried, no model was loaded,
and no image was generated in CI.** The UI display is not evidence of model
compatibility, VRAM headroom during generation, or image quality. Real
Windows UI/video/GPU acceptance remains a separate manual stage.

Related references:
- [Tauri v2 Rust command communication](https://v2.tauri.app/develop/calling-rust/)
- [PyTorch CUDA memory information](https://docs.pytorch.org/docs/stable/generated/torch.cuda.mem_get_info.html)
- [M3-6 GPU QA guide](M3_GPU_HARDWARE_QA.md)
