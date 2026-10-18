# M3-14 — sanitized GPU generation failure classification and guided recovery

This milestone builds on M3-13 read-only VRAM inspection and M3-12's
Windows Tauri **DEBUG-only** generation runner. It introduces strictly
allowlisted failure categories after a user-confirmed image generation
job, without exposing model paths, raw Python stderr or prompts.

## Native failure categories

| `failure_code` | Meaning | Safe recovery |
| --- | --- | --- |
| `cuda_out_of_memory` | CUDA allocator / cuDNN allocation failed | Close other GPU apps; use 512×512, 15 steps; recheck VRAM |
| `python_dependency_missing` | Python inference dependency unavailable | Check local `.venv`, optional inference packages |
| `cuda_runtime_error` | CUDA runtime/driver issue inferred from bounded stderr | Run GPU diagnostic and check driver, CUDA PyTorch |
| `inference_failed` | Failure without a recognized specific cause | Check local offline SDXL files and installed environment |
| `image_verification_failed` | Produced PNG is missing, corrupted or has wrong dimensions/hash | Check output space and local artifact; do not mark success |
| `process_cleanup_failed` | Windows job group termination could not be verified | Inspect whether Python subprocesses remain before retry |
| `execution_timeout` | Inference exceeded 30-minute execution limit | Confirm processes stopped; reduce settings and recheck |
| `user_cancelled` | User requested cancellation | Confirm stopped state before starting another job |

The native Rust process categorizes only a bounded private stderr tail
and known terminal job outcomes. The structured `failure_code` is a
fixed literal string, not a traceback. The existing terminal `phase`
and bounded informational message are preserved; completed successes
have no failure code. A zero-exit child whose PNG verification fails is
**failed**, not successful.

The launch-spawn failure message is sanitized rather than returning an
OS-provided absolute interpreter path. Frontend help uses allowlisted
text and never echoes raw subprocess exceptions. Unknown error types
fall back to general advice.

## Guided recovery in the image generation UI

- A categorized failed, timed-out or cancelled job shows a distinct
  recovery section explaining probable cause and what to check.
- For CUDA out-of-memory and execution timeout only, users can select
  **512×512 · 15스텝으로 변경 (자동 재실행 안 함)**.
- Applying those settings clears previous ordinary GPU consent and the
  separate VRAM-risk acknowledgement. This changes parameters only:
  **no model is loaded, no auto retry occurs**.
- The user can use existing GPU diagnostic / VRAM recheck controls to
  inspect the machine again. The real start command still requires
  explicit consent and a *fresh native* VRAM safety probe.
- Cancellation and Windows process-cleanup errors never lead to automatic
  retries. The operator should inspect lingering processes manually.

## Accuracy and limits

A heuristic stderr classification is an aid to diagnosis, not a
hardware root-cause proof. For example, out-of-memory can be caused
by other GPU software or a particular model/config. PyTorch reports
only allocator-managed CUDA allocations; its peak values exclude some
non-PyTorch/driver allocations.

GitHub CI exercises synthetic stderr, status messages, known failure
categories and frontend advice. It does not execute actual SDXL weights,
an RTX 2060 SUPER, real CUDA-OOM recovery, Windows GUI interaction or
process-tree cleanup on the user's machine. Keep the stacked PR Draft
until Windows Rust CI and real hardware acceptance have been reviewed.

References:
- https://docs.pytorch.org/docs/stable/torch_cuda_memory.html
- https://v2.tauri.app/develop/calling-rust/
- [M3-13 VRAM preflight and recovery](M3_VRAM_PREFLIGHT_RECOVERY.md)
- [M3-12 native GPU gate](M3_TAURI_VRAM_GATE.md)
