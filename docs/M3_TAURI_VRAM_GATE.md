# M3-12 — Windows Tauri native VRAM safety before SDXL generation

M3-12 extends the M3-11 standalone hardware acceptance CLI
safety policy into the **actual Windows Tauri DEBUG** generation workflow.
It does not enable GPU generation in browsers, release apps or HTTP APIs.

## Execution flow

1. User selects registered SDXL safetensors and gives ordinary explicit
   GPU generation consent; Rust rechecks permission and model metadata.
2. Rust takes an exclusive, scoped diagnostic reservation in the JobManager.
   Concurrent windows cannot start a job or a separate CUDA diagnostic.
3. Rust uses a background task to call ONLY the fixed local Python venv
   and backend/gpu_diagnostics.py. Windows Job Objects supervise the
   diagnostic child (25-second bound, strict JSON, no download or model load).
4. CUDA must report ready_for_trial with a valid total/free VRAM snapshot.
   Missing CUDA, invalid memory, Python/probe errors or timeout fail closed.
5. Rust checks the exact same conservative policy as M3-11: total VRAM
   below 6 GiB, currently free VRAM below 4 GiB, or image pixel area
   larger than 768×768 on a GPU with at most 8 GiB total VRAM.
6. When the heuristic blocks an attempt, the app shows an actionable
   message **without loading the diffusion checkpoint**.
7. An additional VRAM-risk checkbox starts **unchecked**. With the
   ordinary GPU consent and a deliberate extra risk acknowledgement,
   a user can opt in to trying a memory-risky generation. Missing CUDA,
   invalid telemetry, unsafe model metadata or release/browser execution
   restrictions CANNOT be bypassed. The starting job shows a warning.
8. The reservation stays active until a supervised child is registered.
   The blocking CUDA probe itself owns the reservation until completion,
   even if the invoking webview closes. On success it transfers the
   reservation back to the launcher until JobManager registers the child.
   An error releases it by RAII, so the system cannot stay locked.
9. Existing Windows Job Objects 30-minute watchdog, cancellation,
   restricted script, bounded PNG decoding, hash and gallery checks remain.

## Interpretation

These thresholds are cautious **engineering heuristics**, not certified
NVIDIA/PyTorch minimums. Free VRAM is a point-in-time observation and
other GPU software can consume it afterwards. CPU offload and different
checkpoints can still produce CUDA OOM when the policy permits an attempt.
Risk acknowledgement is not proof of success.

The native backend always performs a fresh probe. It does **not** trust
potentially stale GPU readings supplied from browser/webview state.
No automatic downloads, network telemetry, Anima/LoRA inference, release
mode GPU command, or arbitrary shell execution has been introduced.

## Automated QA and remaining manual checks

Rust unit tests check normal 8GiB 512×512, low total/free VRAM, high
resolution, invalid contradictory values, separate acknowledgement and
IPC default false. TypeScript checks only the fixed IPC command and
the extra boolean argument, and browser/normal-consent safeguards.

GitHub CI does NOT run actual SDXL inference on the RTX 2060 SUPER,
measure whole-GPU VRAM, visually grade generated PNGs or test GUI
interactions on the user's PC. Actual hardware acceptance and Windows
app process cleanup must still be reviewed before production.

References:
- https://v2.tauri.app/develop/state-management/
- https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- M3_VRAM_SAFETY_GATE.md (standalone CLI policy)
- M3_HARDWARE_ACCEPTANCE_CLI.md (owner-run hardware acceptance)
