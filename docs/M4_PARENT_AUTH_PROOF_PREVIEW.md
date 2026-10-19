# M4-1b — Offline parent-proof contract (CPU-only, no worker process)

## Verified starting point

The new branch stacks on M4-1 [Draft PR #50](https://github.com/nalkarowndal/tyrfghx/pull/50),
commit `0f1a4a6c093e14f259ea6f669ec3dd135902687c`. M3-Final is frozen
but the M2/M3 stacked Draft PRs are NOT owner-approved or merged into `main`.
This is a separately reviewable, non-executing M4-1 increment, **not M4-2 GPU QA**.

## What is implemented

- `backend/inference_worker_auth_preview.py` contains a pure Python 3.12
  stdlib HMAC-SHA256 proof verifier that operates entirely in memory.
- Strict, bounded (at most 4096-byte) UTF-8 JSON with four exact keys:
  `protocol_version: 1`, `operation: "parent_proof"`,
  `request_id: 8–64 ASCII [A-Za-z0-9_-]`, and lowercase 64-character
  `proof` hex. Duplicate/extra keys, wrong version, malformed data,
  huge frames and execution operations fail with a stable error.
- A native parent **would** create fresh, independent cryptographically
  random 32-byte `key` and 32-byte `challenge` per session, and transfer
  them only over a separately protected bootstrap pipe. This step is
  **NOT yet wired to Rust or any real Python child**.
- Future proof formula:
  `HMAC-SHA256(key, b"aiimage-worker-parent-proof-v1\\x00" + challenge + request_id_ascii)`.
  A constant-time `hmac.compare_digest` check verifies a matching
  32-byte digest; domain and request ID bind the proof to this protocol
  and request. The verifier accepts only **one attempt**, even after
  malformed input or a wrong key; replay on the same instance fails.
- Error messages expose no key/challenge/proof, untrusted paths or
  caller-provided fields. Sensitive immutable Python `bytes` cannot be
  guaranteed wiped from RAM; a real worker must minimize their lifetime.
- Automated Linux/Windows `pytest` already collects the new hostile
  input, replay, wrong session, request binding, shape, material and
  no-execution tests without any extra dependency.

## Security boundary — not yet achieved

**This is only a protocol primitive, not a secure IPC implementation.**
Knowledge of a session secret is not independently verified OS process
identity. A real implementation must additionally:

1. Have the **native Rust parent** securely create OS-random per-spawn
   material, deliver it over an owned private pipe (never argv, URL,
   client-accessible API, UI state or logs) and verify peer process identity.
2. Use a bounded bidirectional private IPC framing scheme with one-shot
   handshake deadline, secure cancellation, child exit detection, and
   fail-closed behavior on EOF/crash/timeout.
3. Attach each Windows child process to an owned Job Object before
   permitting worker operations; clean the full process tree on stop.
4. Keep the existing read-only FastAPI process, release GPU feature
   gate and Tauri frontend shell capabilities unchanged. In particular,
   **do not** add unrestricted `shell:allow-spawn` permissions.
5. Independently review isolated venv path, wheel pins/hashes,
   disk budget, package provenance and opt-in installation prior to
   any AI framework load or GPU work.

The module does **not** start a process, open ports, expose FastAPI
routes, touch a model, install packages, run CUDA, generate images,
modify production Tauri permissions, build an installer or merge PRs.

## QA and acceptance

- Run `cd backend && python -m pytest -q test_inference_worker_auth_preview.py`.
  Existing project CI also runs the full backend suite on Python 3.12
  for Linux and Windows, alongside React and locked Windows Rust jobs.
- Confirm this exact branch CI finishes successfully; do not claim a
  hosted Windows installed GUI/GPU acceptance run without evidence.
- PR remains Draft against the preceding M4-1 branch; do not bypass
  stacked-PR owner review.
- Next: native-owned, bounded authenticated transport with actual
  lifecycle tests, still CPU-only and with GPU features disabled.

References:
- [Python hmac / constant-time comparison](https://docs.python.org/3/library/hmac.html)
- [Python secrets / OS randomness](https://docs.python.org/3/library/secrets.html)
- [Tauri v2 sidecar configuration and permissions](https://v2.tauri.app/develop/sidecar/)
