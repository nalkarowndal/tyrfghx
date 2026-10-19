# M2 importer transaction and race regression handoff

**Scope:** [Draft PR #1](https://github.com/nalkarowndal/tyrfghx/pull/1), no merge
or release. Follow-up to [Issue #61](https://github.com/nalkarowndal/tyrfghx/issues/61)
and integration hold [Issue #60](https://github.com/nalkarowndal/tyrfghx/issues/60).

## Implemented cooperative safeguards

- `backend/model_manifest_lock.py` and `src-tauri/src/model_import.rs` use
  the **same** `models/.integrity-write.lockdir` directory name as an exclusive
  cooperative writer guard. Local `mkdir` is exclusive: only one cooperative
  Rust or Python process owns the guard for the full JSON read/modify/replace
  operation. Both fail closed after 10 seconds instead of overwriting
  concurrently. Do NOT auto-remove a suspected stale lock after process crash;
  require owner diagnostics and manual recovery when no writer exists.
- Python now validates the safetensors metadata and hashes/copies bytes from
  the **same opened source file descriptor** rather than validating by
  pathname and later re-opening. Rust already validates/reads one file
  handle, but both platforms still have a path-check/open gap against
  malicious reparse-point replacement.
- Validate an existing registry before publishing the new model file so
  corrupt manifest cases fail early. After a **post-publish** registration
  failure, neither importer now deletes a destination pathname whose identity
  could have changed. The unregistered file is retained with an error requiring
  manual reconciliation; no successful registration is claimed.
- Python negative QA tests: concurrent imports and manifest updates, stale
  guard remains intact on timeout, a Linux source-path swap after open
  preserves the pinned source byte stream, and simulated post-publish failure
  does not delete an externally replaced destination. The path-swap test
  skips where Windows does not permit deleting an opened fixture file.
- Windows Rust QA: concurrent fake imports preserve every registry ID;
  intentionally corrupt existing registry refuses publication without changes.

## Limitations and next security review

- **Not a hostile-filesystem transaction guarantee.** Cooperative mkdir locks
  do not stop processes ignoring the lock or an actor with permission to
  replace the lock directory, root or manifest. Waiting processes never
  forcibly clear stale locks.
- Windows native source opening still checks a pathname separately from
  `File::open`; a privileged concurrent actor could change it between
  operations. No production handle-relative Win32 traversal is implemented.
- The Rust and Python failures preserve any copied-but-unregistered files
  rather than risking the wrong unlink; future UI should expose a local,
  owner-approved reconciliation flow after checking live hashes.
- Concurrent Rust+Python live mixed-process competition is covered by the
  **shared lock protocol and independent tests**, but a real Windows
  cross-language process test must be added to prove interoperability in
  an installed application.
- Header inspection is metadata-only; it is not proof of model safety,
  inference compatibility, or publisher provenance. No GPU, torch,
  model weights, downloads or pip installations were used.
- **All subsequent stacked PR branches #2–#59 were forked before this
  PR #1 amendment.** These fixes are NOT present on their existing heads.
  With explicit owner approval, propagate via reviewed rebase/retarget
  in dependency order and rerun exact-head CI. Do not merge or retarget
  automatically.

## Acceptance checklist

- [ ] PR #1 updated exact-head frontend/Node, Linux Python, Windows Python
  and Windows Rust CI all succeed.
- [ ] Existing local import/no-clobber and corrupted-registry regressions
  continue to pass.
- [ ] Separate native Windows no-follow file-open and cross-language
  process tests are reviewed before calling arbitrary filesystem
  access production-safe.
- [ ] Human security review / branch protection / owner-approved
  integration remain blockers in Issue #60.

References:

- [Microsoft Win32 reparse points](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)
- [Python msvcrt and file operations](https://docs.python.org/3/library/msvcrt.html)
- [Rust std::fs::File and locking](https://doc.rust-lang.org/std/fs/struct.File.html)
- [Tauri 2 app command capabilities](https://v2.tauri.app/security/capabilities/)
