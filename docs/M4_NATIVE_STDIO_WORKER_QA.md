# M4-1c — Native owned stdio worker QA (Windows tests ONLY)

## Baseline and scope

This increment stacks on M4-1b Draft PR #51, commit
`ec9ee280bcec882a4b4df10ae2374469c23ffb8f`. M4-1b general CI
completed 4/4 success in
[workflow #39217054999](https://github.com/nalkarowndal/tyrfghx/actions/runs/39217054999).
M3/M4 earlier Drafts are NOT merged to `main` and need owner review.

**M4-1c is a real Win32 process/pipe TEST HARNESS, not production worker support.**
No Tauri command, frontend feature, FastAPI route, runtime installer, webview
shell permission, GPU action or model access is introduced.

## Code under review

- `backend/inference_worker_stdio_fixture.py`: checked-in Python standard
  library fixture. Reads a <=4096-byte single-line JSON bootstrap via stdin,
  sends a single HMAC-SHA256 proof via stdout, then accepts only existing
  no-execution `describe` contract. Invalid/duplicate keys, oversized
  frames and unsupported operations fail without printing user input.
  Tests can select hard-coded `success`, `tamper`, `oversize`,
  `stall`, `crash` behavior. No user-provided executable arguments.
- `src-tauri/src/inference_worker_stdio_qa.rs`: compiled ONLY under
  `#[cfg(all(test, windows))]` via `lib.rs`. Starts the fixed fixture with
  `python -I -S`, cleaned Python environment and anonymous stdin/stdout
  pipes. The child is created suspended and assigned to the existing native
  kill-on-close Win32 Job Object before resuming. Rust sends test bootstrap,
  validates an exact proof schema plus HMAC, then reads a bounded CPU-only
  `describe_result`. The reader has a fixed frame bound and timeout.
  All paths (success, wrong proof, oversize, crash and stall) attempt
  full Job Object termination and verify it is drained.
- The Windows Rust CI job explicitly selects Python 3.12 for repeatability.
  It runs the ordinary locked `cargo test --lib --locked`, which discovers
  these Win32 native tests. CI tests neither PyTorch/CUDA nor real models.

## Explicit security boundaries

1. The fixture uses **deterministic 32-byte synthetic test keys/challenges**
   and exchanges them through inherited anonymous pipe handles. This is for
   repeatable **test behavior**, NOT production credentials or native peer
   authentication. A production implementation needs fresh OS-random
   per-session secrets, secure key delivery, executable provenance checks,
   one-attempt authentication, peer/handle ownership checks and bounded
   session expiry.
2. The test verifies proof bytes in constant-time after canonical parsing,
   but proof of a secret sent to a child itself does not prove its binary
   provenance. Do not describe this harness as completed production IPC.
3. Rust's existing Win32 Job Object manager already configures
   `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Test only reuses it; release
   startup, frontend permissions and read-only FastAPI ownership are
   deliberately unchanged.
4. Local `python` resolution from the pinned CI environment is acceptable
   ONLY in this checked-in test harness. The actual app must not execute an
   arbitrary PATH Python and must verify a trusted user-approved runtime.
5. No output data is written, no model file is opened, and no runtime
   dependencies are installed. RTX 2060 SUPER compatibility is unknown;
   **M4-2 consented GPU validation is still future work**.

## Acceptance gates

- [ ] Exact-head Linux frontend/Node mocked E2E build and tests PASS.
- [ ] Exact-head Linux Python and Windows Python tests PASS.
- [ ] Exact-head Windows Rust locked tests PASS including native subprocess
  roundtrip, invalid proof, oversize, stall/crash cleanup.
- [ ] Review test harness for any accidental production registration and
  keep all staged PRs Draft until owner approval.
- [ ] Real end-user inference-worker IPC with authenticated parent-owned
  runtime, explicit consent and isolated venv: NOT implemented.

References: [Microsoft Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects),
[Python subprocess](https://docs.python.org/3/library/subprocess.html),
[Python HMAC](https://docs.python.org/3/library/hmac.html),
[Tauri v2 security](https://v2.tauri.app/security/).
