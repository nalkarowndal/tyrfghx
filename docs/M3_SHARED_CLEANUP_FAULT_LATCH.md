# M3-17 — shared GPU process-cleanup safety latch

## Change summary

M3-16 verifies that no active processes remain in the Windows Job Object
after a user-confirmed local SDXL generation. The *generation* job state
already prevented another GPU run if its process-group cleanup was
unverified. However, the separate CUDA-only diagnostic and read-only VRAM
preflight use independently supervised Windows Job Objects. Their
cleanup failure previously returned an error without retaining the same
session-wide safety lockout.

M3-17 adds one `Arc<AtomicBool>` **cleanup fault latch** to the existing
Tauri `JobManager`, shared across all three routes:

- Explicit Windows DEBUG SDXL generation.
- Read-only CUDA environment diagnostic (`inspect_local_gpu`).
- Read-only per-resolution VRAM check and the preflight run immediately
  before actually launching SDXL.

When a supervised process group's termination call or its
`ActiveProcesses == 0` verification fails, the owner sets the flag
**before releasing the single-flight diagnostic permit or finalizing
job status**. An error is returned, but the flag stays set for the
lifetime of the desktop app process. No frontend request, checkbox,
safe preset, or succeeding later cleanup may clear it.

Every subsequent `JobManager::reserve_diagnostic` attempt fails before
spawning Python or probing CUDA, whether or not a generation snapshot
exists. This also blocks the previously missing case where **only** a
read-only GPU diagnostic failed and the job snapshot remained idle.

## Diagnostic cleanup paths

The fixed offline GPU diagnostic now calls one shared helper to
terminate and verify its Windows Job Object in all attached-child
exit paths:

1. Normal successful or unsuccessful diagnostic subprocess exit.
2. Diagnostic timeout (25 seconds), after which best-effort child kill
   and wait are still attempted.
3. Failure to retrieve the subprocess exit status.
4. Unexpected inability to obtain the diagnostic stdout channel.

The helper polls up to 2 seconds, checks the whole Job Object rather
than just the parent PID, and latches any failure. A timeout with
successful cleanup is **not** a persistent cleanup fault: it can be
retried after the command returns, subject to the existing single-flight
guard. Failure of Job Object creation/assignment before the process
can run is already fail-closed separately; these new paths concern
attached, running supervised groups.

The explicit image generation worker likewise stores a cleanup fault
when its termination or verified group-drain step fails. Existing
`process_cleanup_failed` job snapshots and their Korean messages are
preserved.

## User recovery

A failed cleanup shows an actionable Korean warning to inspect related
processes in **Windows Task Manager**, confirm they are no longer
running, and restart the app. No silent retry or "reset GPU" command
has been added. The UI does not display raw Python stderr, local model
paths, filesystem exceptions, or process internals.

## Tests and limitations

- Rust unit tests verify the shared JobManager latch remains active
  across reservations and that diagnostic cleanup outcomes never
  automatically clear a prior failure.
- TypeScript unit tests verify the new process-cleanup warning is
  shown before generic OOM, Python or overlapping-job help and does
  not expose example private paths.
- All previously established Windows OS Job Object fixture tests
  remain. Linux/Windows Python and frontend regression tests remain.

CI has **no access to the user's RTX 2060 SUPER 8GB or loaded SDXL
weights**. Tests do not prove that terminating a Windows process group
reclaims all CUDA device memory, that all GPU drivers reset safely, or
that the GUI handles real OOM/cancellation successfully. Manual
Windows hardware acceptance remains required.

Technical references:
- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject
- https://doc.rust-lang.org/std/sync/atomic/struct.AtomicBool.html
- M3_VERIFIED_PROCESS_CLEANUP.md
