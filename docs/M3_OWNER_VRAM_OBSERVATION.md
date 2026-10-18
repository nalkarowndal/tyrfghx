# M3-18: Owner-run NVIDIA VRAM observation for Windows QA

This is an **owner-operated read-only system GPU memory observer**, used alongside the Windows Tauri DEBUG image generation UI. It is not an automatic GPU benchmark or acceptance certificate.

## Why observe VRAM separately?

GitHub Actions cannot execute real SDXL inference on the user's RTX 2060 SUPER 8GB. M3-16/M3-17 verify Windows Job Object process-group cleanup; an empty group does **not** mean the NVIDIA driver has immediately returned memory. PyTorch allocator peaks also do not measure all GPU allocations.

NVIDIA documents that nvidia-smi supports CSV GPU properties but that Windows WDDM device-level memory reporting and GeForce support may be incomplete. Metrics may be unavailable or N/A. Unavailable readings are **inconclusive**.

## Windows manual procedure

From a PowerShell terminal at the repo root, use the project's already installed Python 3.12 virtual environment:

~~~powershell
.\.venv\Scripts\python.exe backend\gpu_memory_observer.py --observe --confirm-monitor --gpu-index 0 --duration-seconds 120 --interval-seconds 2
~~~

The tool **requires both opt-in flags**. Allowed duration is 10–900 seconds; interval is 1–10 seconds. The GPU index is a fixed integer 0–16. The monitor produces a JSON report in the terminal only; it does not save, upload or transmit anything by itself. Output redirection to a private local file is the operator's separate choice.

During the observation window, manually run the Tauri DEBUG UI, with separate model selection and explicit GPU-run approval. Use an authorized SDXL checkpoint, proper local offline config and GPU-enabled PyTorch. First try 512×512, 15 steps, one image; inspect the actual result visually. For cancellation QA, start another manual generation, cancel it from the UI and inspect Windows Task Manager for leftover Python processes. Run additional separate observation windows where useful.

The tool uses only fixed NVIDIA command-line arguments, with no shell and no model/prompt/path provided by the user:
nvidia-smi --query-gpu=index,memory.total,memory.used,memory.free --format=csv,noheader,nounits

Each sample subprocess is subject to a 4-second timeout. Bad or missing CSV readings, a changing GPU total, N/A data or an unavailable executable stop sampling with a sanitized error category and partial-observation state.

## Report interpretation

The report contains sampled start/peak/end **system-wide** GPU used memory (MiB), corresponding free memory at end, differences from baseline, sample count and sample interval. A successful observation means **sampling succeeded**, not that inference, cancellation, PNG quality, network isolation or memory reclamation was validated.

The manual checks for process cleanup, visual quality, offline network isolation and attribution of reclaimed CUDA VRAM remain **not_tested**. Sampling may miss short-lived spikes. Other programs and Windows driver memory reservations can change the totals. A close-to-baseline final result is NOT proof of job-specific VRAM release.

No model is loaded, GPU driver reset, process terminated or CUDA allocations intentionally created by this monitor. GitHub CI uses mocked nvidia-smi output and injected samples only; no RTX 2060 SUPER hardware runs there.

## References

- NVIDIA system management utility: https://docs.nvidia.com/deploy/nvidia-smi/
- PyTorch GPU memory measurement scope: https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- M3_HARDWARE_ACCEPTANCE_CLI.md: owner-run explicit image inference workflow
- M3_SHARED_CLEANUP_FAULT_LATCH.md: session GPU process cleanup lockout
