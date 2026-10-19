# M4-1e — Synthetic-only local wheel byte-integrity QA

## Baseline

M4-1d [Draft PR #53](https://github.com/nalkarowndal/tyrfghx/pull/53)
final parent SHA `c691180fbbbb8515f2978cf13a2d7789a255694d`
passed four routine CI jobs on [push run #39238121050](https://github.com/nalkarowndal/tyrfghx/actions/runs/39238121050).
M2/M3/M4 prior Drafts remain **unmerged** and still need owner security review.
This M4-1e increment is a **test fixture**, not production installation readiness.

## Implemented and test scope

- `backend/inference_wheel_fixture_integrity.py` depends only on Python stdlib
  and the preceding read-only `inference_install_preview.preview` parser.
- The manifest cannot specify a filesystem path or URL: only strict
  allow-listed wheel basenames; it remains bounded to 32 KiB, one exact
  pinned-version entry per distribution, and SHA-256 **digest format**.
- A separately provided absolute Python `Path` must be an existing
  **isolated synthetic QA directory** containing exact
  `.aiimage-m4-1e-synthetic-fixture` marker bytes. Files are read-only;
  directory contents are never extracted, installed, executed or modified.
- For every mock wheel-named file, check regular-file type, reject visible
  symlink/junction/reparse attributes and hardlinks, require exact declared
  size and resolved parent within fixture root, bound each synthetic
  file to **8 MiB**, stream SHA-256 in 256 KiB chunks, compare digest
  in constant-time and re-check open handle identity/size/mtime.
- All exceptions are mapped to constant rejected status and never echo
  private paths, file contents, tokens or raw exceptions. Cancellation
  skips parsing and filesystem reads. Tests generate mock files in pytest
  `tmp_path`; they are *not* real or installable Python wheels.
- A successful report is `synthetic_fixture_verified`, *not*
  `wheel_safe_to_install`. Production authorization, source provenance,
  wheel archive ZIP validity, runtime/driver/CUDA compatibility, and
  user-approved path checks all remain **false**.
- Tests cover mock-byte match, altered same-size bytes, wrong digest,
  wrong declared size, missing file, >8 MiB cap, wrong/missing marker,
  symlinked file/root, manifest traversal/URL attempts, cancellation,
  invalid JSON and absence of any new API/runtime operation.

## Security limitations

This QA utility is not a general-purpose safe path verifier. In particular,
Windows Python `os.open` does not supply a complete verified
`FILE_FLAG_OPEN_REPARSE_POINT` and handle-relative, component-by-component
reparse-safe path walk. Pre-open `lstat` plus after-open `fstat` reduce
ordinary mistakes but **cannot eliminate all adversarial Windows race
conditions**. The fixture marker is only a QA convention, not an
authorization primitive or trusted signature. No private user-supplied
directory, Python installation, checkpoint, LoRA, or actual third-party
package artifact is read by CI.

Before any production local package inspection:

1. Explicit user consent and native absolute runtime / source-directory
   selection without allowing arbitrary traversal from the webview.
2. Native Win32 handle-based `CreateFileW` file/directory validation,
   no junction/reparse traversal, protected directory guards and
   robust cancellation/race handling with approved scopes.
3. Verify **complete transitive** wheel dependency versions, platform
   tags and official release provenance separately. Matching SHA-256
   to an attacker-provided expected hash is not sufficient trust.
4. Only then build a fully hash-pinned lockfile; for actual installation
   pip recommends `--require-hashes` and `--only-binary :all:`.
   Review package policies and obtain separate install approval.
5. Keep model files, installed Windows backend, read-only APIs,
   production GPU-disabled policy, CSP and installer defaults unchanged.

## QA gates

- [ ] Exact-head Linux/Windows Python `pytest` passes new fixture tests.
- [ ] Frontend build/Node mock tests and locked Windows Rust CI pass.
- [ ] No source-file / runtime permissions or new webview/sidecar commands.
- [ ] Parent PR chain owner-reviewed and explicitly approved before merge.

References:
- https://pip.pypa.io/en/stable/topics/secure-installs/
- https://docs.python.org/3/library/hashlib.html
- https://docs.python.org/3/library/os.html
- https://v2.tauri.app/security/capabilities/
