# M2 read-only orphan model review — advisory preview only

**Current stage:** M2 PR #1 Draft, follow-up to [Issue #61](https://github.com/nalkarowndal/tyrfghx/issues/61) and [Issue #60](https://github.com/nalkarowndal/tyrfghx/issues/60). This is a non-authorizing planning helper, **not** an automatic recovery or installation feature.

## Problem and narrow solution

A safetensors copy can have been published successfully but its registration in
`integrity.json` can fail. The importers deliberately preserve the file rather
than blindly unlink the destination pathname, which might have been replaced by
another actor.

The existing read-only `model_catalog.scan_models()` labels that copy
`integrity_state="not_recorded"`. The new
`backend/model_reconcile_preview.py` provides a **pure, in-memory advisory
classification** of that existing catalog observation and an already-supplied
manifest entry/safety verdict. It never opens paths, scans directories, hashes
weights, mutates a registry, deletes copies, launches models, downloads
dependencies, or starts a GPU.

- A valid cached safetensors observation, no current manifest entry, and a
  trusted-by-caller *parseable* manifest status yield
  `status="review_required"` only. The helper does **not** establish the
  authenticity of that manifest.
- Malformed catalog identity (unapproved ID/category/name), missing observations,
  invalid headers, CKPT, empty files, and contradictory manifest state reject.
- Existing registered entries produce `not_an_orphan`, never a recovery
  overwrite action. Corrupted/unsafe manifest state produces
  `invalid_manifest`.
- Every result explicitly reports `can_register=false`,
  `can_delete=false`, `can_execute=false`,
  `requires_human_review=true`, `files_opened=false`,
  `files_modified=false`, and `trusted_provenance_verified=false`.
- No new FastAPI route, CLI command, Tauri command, webview capability,
  file picker, background repair process, or user consent UI is introduced.

`backend/test_model_reconcile_preview.py` asserts that the helper never
performs I/O, including a simulated failed import of a tiny disposable synthetic
safetensors file. The latter is listed by the existing catalog, with no
`integrity.json` silently created or modified.

## Critical trust boundaries

**`manifest_ok=True` is caller-supplied and NOT an attestation.**
The helper cannot authenticate live file identity, actual SHA-256, publisher
provenance, a trusted expected digest, or immutable filesystem ownership. It
must NEVER be used to authorize a production registration without independently
verifying those inputs through a reviewed native secure-file API.

An actual future owner-approved recovery flow would require:
1. An explicit native file-selection or app-root review action; no arbitrary
   webview-controlled paths.
2. Handle-relative, securely pinned Win32 root/ancestor validation and no-follow
   final-file opening, with identity checks and adversarial race QA.
3. Live bounded hashing of that pinned object, safetensors header validation,
   independent trusted provenance / expected digest, and comparison against
   the user's expected source.
4. User-visible preview and explicit confirmation before any mutation.
5. One cross-language writer transaction that rejects changed file identity
   and existing conflicting entries; a crash-safe rollback/recovery audit.
6. Fresh end-to-end Windows install/update QA in a disposable isolated profile.

Existing M4 synthetic ZIP and native fixture QA **do not satisfy** these
production requirements.

## Acceptance criteria

- [ ] Exact-head Linux Python, Windows Python, frontend and Windows Rust CI
      PASS (the old #1 CI cannot stand in for the new head).
- [ ] No real model/cache files, wheel archive, package installer, GPU or CUDA
      device accessed.
- [ ] New helper remains read-only and unexposed through privileged APIs.
- [ ] Issue #61 remains OPEN; PR #1 remains Draft, and the long downstream
      Draft stack remains subject to owner-approved synchronization/merging.

References:
- https://docs.python.org/3/library/os.html
- https://docs.python.org/3/library/pathlib.html
- https://v2.tauri.app/security/capabilities/
