# M3-5 — Windows Job Objects: process-group supervision

## Why this change?

The earlier M3-4 runner used Rust `Child::kill()`, which stops the direct
Python process but does not by itself supervise its descendants. For a local
AI inference workload that may use subprocesses or data-loading helpers, this
can leave work running after cancellation.

M3-5 adds a **Windows-only process group** using official Win32 Job Objects,
based on Microsoft documentation:
- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject

The implementation is in `src-tauri/src/windows_process_job.rs`.

## Process lifecycle

1. Tauri (still **Windows DEBUG only**) accepts a bounded settings object,
   requires explicit consent, and selects the **fixed** repository-local
   `.venv/Scripts/python.exe` and `backend/generate_sdxl.py`. No frontend
   executable path, shell command or network model download is allowed.
2. Rust calls `CommandExt::creation_flags(CREATE_SUSPENDED)` to start Python
   without running user-space instructions.
3. Rust creates a Job Object, sets
   `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, assigns the suspended process via
   `AssignProcessToJobObject`, and resumes its primary thread using the
   documented Windows thread-snapshot / `ResumeThread` APIs.
4. If setup fails, Python is killed/awaited and the operation fails closed.
   There is no fallback to running Python ungrouped.
5. Cancellation and the 30-minute watchdog call `TerminateJobObject`.
   After the direct Python process exits, Rust calls it again before
   reporting terminal status, to clean up remaining associated descendants.
6. The Job Object handle is owned by a RAII wrapper and is closed on drop.
   Kill-on-close requests termination of processes still assigned to the
   group. On app shutdown, Rust also requests job termination.

### Guarantees and exceptions

- Standard subprocesses that inherit the parent Job Object are managed
  together. The code does not request breakaway permissions.
- Windows Job Objects do not automatically cover *every possible* process
  launched by a different mechanism or services outside the job.
- Job assignment may fail in constrained/sandboxed environments; the
  launcher **fails closed** rather than permitting untracked inference.
- `TerminateJobObject` requests group termination, but does not prove
  GPU driver cleanup or complete VRAM reclamation.
- Inference may still fail due to unsupported model weights, inadequate
  RTX 2060 SUPER 8 GiB VRAM, drivers or mismatched packages.
- The release build and browser GPU-execution paths stay disabled. No
  unauthenticated FastAPI execution endpoint has been added.

## Automated tests

Windows Rust CI exercises a real fixed `cmd.exe` fixture in a suspended
Job Object. It checks both normal completion and group termination of a
long-running *non-GPU* process, along with earlier Rust unit tests.
Frontend and Python regression tests continue unchanged.

These tests do **not** prove actual parent-and-grandchild termination in
every scenario, and do not load weights or run CUDA. Full manual acceptance
on Windows should observe process-tree behavior in Process Explorer/Task
Manager after pressing Cancel, watchdog termination, app shutdown, and
simulated subprocesses. The RTX 2060 SUPER test must separately record
driver, CUDA/PyTorch version, checkpoint, actual GPU VRAM use, and PNG output.

## Next

Use Windows GUI and GPU hardware QA to verify end-to-end generation and
process cleanup. Only then consider production packaging / signing, secure
owner-only runtime configuration and enabling the release generation button.
