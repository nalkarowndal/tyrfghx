# M4-1 — First CPU-only worker contract slice (NO execution)

## Context and verified baseline

The predecessor M3-Final branch `chore/m3-final-readiness-audit` at SHA
`e564a14f3ec6277c033b234950610b992c25a665` passed:

- [General CI #39187526269](https://github.com/nalkarowndal/tyrfghx/actions/runs/39187526269): **4/4 PASS** — frontend/Vitest, Linux + Windows Python, and Windows Rust.
- [Actual hosted Windows backend/NSIS/GUI QA #39187461951](https://github.com/nalkarowndal/tyrfghx/actions/runs/39187461951): **PASS**, including authenticated frozen backend, two-version update, rejected downgrade, preinstall failure/retry, real GUI backend restart, and safe uninstall with synthetic models/outputs preserved.
- M3-Final [Draft PR #49](https://github.com/nalkarowndal/tyrfghx/pull/49) is **unmerged**; the earlier dependent M2/M3 stack must be reviewed and owner-approved before any `main` integration.

The owner requested starting the next phase. This M4-1 Draft is a
**provisional branch based on the proven M3-Final snapshot**; it does
not mean the inherited PR stack has already been integrated.

## Why a separate inference worker?

The existing bundled Python FastAPI API is deliberately read-only:
it owns the native model catalog, package metadata and health checks
but **does not** contain or run PyTorch/Diffusers/CUDA inference. The
M3-46 runtime plan recommends a separate Python virtual environment
whose dependencies are user-selected and installed only after explicit
approval. Python's official `venv` creates isolated site-packages,
and Tauri supports packaging separate binaries, but this first
increment **does not create a venv or package a new sidecar**.

## Actual code in this slice

`backend/inference_worker_contract.py` defines a pure Python protocol
**preview**. It is deliberately NOT imported by the existing app API
and is not registered as a FastAPI route or native Tauri command.

- Strict protocol version **1** (reject bool, float, obsolete or future versions).
- Bounded **4096-byte UTF-8 JSON** frame; duplicate keys and non-JSON
  payloads rejected, with a fixed sanitized error code.
- An **exact, three-key request**: `protocol_version`,
  `operation="describe"`, and ASCII `request_id` (8–64 restricted chars).
  Extra keys, filesystem paths, model names, hardware flags,
  package-install requests and all future executor operations are
  rejected before a response.
- A deterministic `describe_result` states
  `worker_state="not_connected"`,
  `launch_enabled=false`, `connection_ready=false`,
  `requires_native_parent_authentication=true`,
  `requires_explicit_gpu_consent=true`,
  `requires_isolated_python_environment=true`, and
  `cuda_tested/models_opened/downloads_performed/packages_installed=false`.
- Only the validated, safe `request_id` is echoed from the request.
  No raw exception text, paths, bearer tokens, prompts, model content,
  GPU details, secrets or device identifiers enter the result.
- No sockets, child processes, Rust integration, GPU probe, module
  imports of AI libraries, downloads, installs or disk writes exist.

`backend/test_inference_worker_contract.py` exercises valid
no-execution frames, invalid versions, unknown operations, duplicate
JSON keys, oversize/invalid UTF-8, request-ID injection, non-bytes
input and the absence of a live generation route in the packaged API.
Both existing Linux and Windows Python `pytest` jobs run these
tests; no new CI privileges or external services are required.

## Deliberately unimplemented: NEXT M4-1 slices

1. Native Tauri parent authentication handshake and per-session
   ephemeral key management **not yet implemented**. Static request
   validation alone is not authentication. Never expose this
   preview over an unauthenticated localhost TCP endpoint.
2. Owned child process management, Windows Job Object lifecycle,
   timeout, crash cleanup and process-tree cancellation **not yet
   connected** for the separate inference worker. Reuse, but do
   not accidentally weaken, the proven packaged backend manager.
3. Runtime directory selection, install preview, wheel pins/hashes,
   wheel provenance verification, disk budget and OS permissions
   need independent reviewed code. No venv, pip or packages
   installed in this slice.
4. Explicit user consent, driver/GPU probing, Torch import, checkpoint
   access, CUDA allocations and inference are **future opt-in
   milestones**, not implied by compiling this module.
5. Production CSP, signed Windows installer and clean-PC deployment
   remain M3 inherited release blockers. Don't ship GPU mode
   or Tauri shell execute permissions from this change.

## Exit criteria for THIS slice

- New branch Linux/Windows Python unit tests pass the malicious
  input/no-execution protocol cases.
- Frontend React/Vitest/Node and locked Windows Rust CI remain green.
- Existing auth-gated packaged read-only API and Tauri defaults
  are untouched. No real Windows installer triggered by this branch,
  so don't infer installer QA pass from ordinary CI.
- M3-Final remains an unmerged Draft; M4-1 stays Draft and
  `main` unchanged until explicitly approved.

Sources:
- https://docs.python.org/3/library/venv.html
- https://v2.tauri.app/develop/sidecar/
- https://docs.github.com/en/pull-requests/reference/stacked-pull-requests
