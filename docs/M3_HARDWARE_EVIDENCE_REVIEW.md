# M3-19 — Offline hardware QA evidence review

M3-19 combines **two owner-supplied local JSON reports** to help a human review
a real Windows machine. It **does not** execute CUDA or SDXL, inspect local
PNG bytes, certify hardware, attribute GPU memory usage to this app, or
validate which computer actually produced the JSON.

## Required input sources

1. **M3-10 hardware acceptance report:** Produced by
   `backend/hardware_acceptance.py`. A true explicit SDXL test requires
   both `--execute` and `--confirm-gpu`, a local authorized SDXL
   checkpoint/config and CUDA-enabled PyTorch. Metadata-only runs are
   supported as **incomplete** evidence.
2. **M3-18 system VRAM observation:** Produced by
   `backend/gpu_memory_observer.py --observe --confirm-monitor`
   while the operator separately starts a local GPU job from the Tauri
   Windows DEBUG app or the standalone acceptance CLI. The observer
   never runs a model and reports nvidia-smi system-wide snapshots only.

Generate each report separately on the owner PC and save each JSON
output as **UTF-8 without a BOM**. PowerShell 7 UTF-8 output encoding is
recommended; older Windows PowerShell redirect encoding differs.
Do not publish locally saved evidence without reviewing it first.

Once both files exist, from the repository root run:

~~~powershell
.\.venv\Scripts\python.exe backend\hardware_evidence_review.py --generation-json ".\generation-report.json" --gpu-memory-json ".\vram-report.json" --confirm-review
~~~

The CLI requires deliberate `--confirm-review` before reading files,
does no subprocess calls, no network activity and no file writes, and
prints a sanitized JSON summary to the current terminal.

Each JSON input is limited to 64KiB. Symlink inputs, duplicate fields,
non-standard NaN/Infinity JSON, unsupported source versions, mismatched
status fields and contradictory GPU measurements fail closed.

## Evidence interpretation

The tool has only two valid review states:

- `evidence_available_for_manual_review`: The M3-10 report **claims**
  it verified and decoded a PNG with SHA-256, and the M3-18 report
  **claims** a complete system-level GPU observation session. These
  **are untrusted self-reported inputs**; this state is not hardware
  qualification and does not independently validate the PNG or GPU.
- `incomplete_evidence`: A source is metadata-only, a failed CUDA
  attempt, a cancelled/partial nvidia-smi observation or similar.
  No readiness is inferred.
- Invalid/malicious input is rejected with `invalid_evidence` and
  an allowlisted error code. No input path, private prompt or unknown
  source field is echoed.

The summary includes the **SHA-256 of each original input JSON byte
sequence** so the owner can associate it with retained original files;
the digest does not prove that the source software or GPU was genuine.
Only allowlisted measurements, dimensions and safe metadata are copied
from the inputs.

All manual checks remain **not_tested**, irrespective of any arbitrary
`manual_checks` fields in input JSON:

- Visual prompt adherence and PNG pixel quality.
- Windows process-tree cleanup after generation/cancellation.
- Attribution of freed CUDA VRAM to this particular app.
- Windows GUI interaction.
- Offline network isolation.
- Confirmation that the two reports describe the same GPU/session.

The real GPU may be unavailable, nvidia-smi may return N/A on Windows
WDDM, a sampler can miss spikes, and the observer captures system-wide
VRAM from unrelated processes. Neither matched sample sizes nor a
near-baseline final reading prove memory reclamation.

## Security and build status

The new script is an offline, **read-only operator tool**, not a Tauri
command, automatic CI hardware benchmark, HTTP endpoint or remote
agent. It never executes arbitrary input, scripts, nvidia-smi, Python
model generation or a GPU reset. It does not turn Draft PRs into
production releases.

GitHub Actions unit tests use synthetic JSON and temp files only.
The owner's **RTX 2060 SUPER 8GB has not been accessed**, and real
SDXL rendering and GUI cancellation remain independent manual QA.

References:
- [Python strict JSON parser behavior](https://docs.python.org/3/library/json.html)
- [NVIDIA nvidia-smi telemetry limitations](https://docs.nvidia.com/deploy/nvidia-smi/)
- [M3-10 hardware acceptance](M3_HARDWARE_ACCEPTANCE_CLI.md)
- [M3-18 NVIDIA observer](M3_OWNER_VRAM_OBSERVATION.md)
