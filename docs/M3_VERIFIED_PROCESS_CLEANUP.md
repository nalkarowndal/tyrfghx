# M3-16 — verified Windows process-group cleanup

This milestone strengthens process termination verification for the Windows
Tauri DEBUG-only offline SDXL generator and its CUDA diagnostics.

## Problem addressed

Before M3-16, calling `TerminateJobObject` and receiving success was
treated as adequate for finishing a generation job. However, success
from the termination API is distinct from independently confirming
that every process in the supervised Windows Job Object has exited.

The check must cover the entire group, not just the parent Python PID.
A parent process can exit while its helpers or children remain active.

## New bounded process cleanup verification

The Windows-only `ProcessJob::verify_drained(Duration)` method:

- Calls `QueryInformationJobObject` using
  `JobObjectBasicAccountingInformation`.
- Reads `JOBOBJECT_BASIC_ACCOUNTING_INFORMATION.ActiveProcesses`.
- Requires exactly **zero active processes** in the job.
- Checks repeatedly at 50ms intervals for up to the passed bounded
  duration (2 seconds for generation and the diagnostic).
- Returns a sanitized error if the Job Object query fails or the
  active process count never reaches zero.

When Python exits (whether success, user cancellation, timeout or a
generation failure), the generation worker first calls
`TerminateJobObject`, then checks `verify_drained(2s)`.
If either operation fails, the final job state is
`failed`, with error code `process_cleanup_failed`, regardless
of the previous outcome. It does **not** mark an unverified cancellation
as completed or the PNG as successful.

The read-only CUDA diagnostic also requires a verified empty Windows
Job Object after normal completion before returning diagnostic data.

Existing protections remain in force: fixed offline scripts, single
active job, explicit user confirmation, VRAM gates, Windows Job Object
kill-on-close semantics, 30-minute generation deadline and bounded
private-stdin request protocol.

## Windows CI coverage

- Existing live Windows Job Object tests already ensure the fixture
  process can run, terminate and return a non-success exit code.
- A new fixture starts a long-lived `cmd.exe` subprocess and checks
  that `verify_drained` fails while it remains active, then passes
  after `TerminateJobObject` and a bounded exit wait.
- Rust pure tests assert that failed group cleanup cannot leave a job
  marked `succeeded`, `cancelled`, or `timed_out` and produces a
  stable `process_cleanup_failed` code without sensitive paths.

The CI fixtures are Windows OS processes, **not SDXL or GPU workloads**.
They cannot establish actual RTX 2060 SUPER 8GB inference,
CUDA-memory reclamation, visual quality or GUI cancellation success.
Owner-PC manual QA is still required.

## Fail-closed and remaining limitation

If Job Object state cannot be queried, the app rejects a success
result and asks the user to check Task Manager. The process
lifecycle has a bounded cleanup check instead of optimistic success.
This cannot prove that the GPU driver immediately returned all VRAM,
nor can it find processes that legitimately escaped Job Object
assignment through external means. The fixed Windows process group
assignment and kill-on-close safeguards remain critical.

References:
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_basic_accounting_information
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject
- https://doc.rust-lang.org/std/process/struct.Child.html
- M3_PRIVATE_GENERATION_STDIN.md
