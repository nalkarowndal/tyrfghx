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
- Native Windows model source opening now uses
  `OpenOptionsExt::custom_flags(FILE_FLAG_OPEN_REPARSE_POINT)` and checks
  `FILE_ATTRIBUTE_REPARSE_POINT` on the **opened file handle**, rejecting
  the final-component symbolic link/reparse point. An attacker could still
  race the **ancestor directory** path or replace filesystem objects; a
  full trusted-root handle-relative Win32 traversal is NOT implemented.
- A new Python **read-only catalog regression** deliberately fails the
  `integrity.json` registration after publishing a tiny valid synthetic
  safetensors file, then confirms `scan_models` still lists that file as
  `integrity_state="not_recorded"` with no trusted recorded SHA and does
  not create/repair a manifest or modify the copied bytes. This is a
  *manual reconciliation diagnostic*, not an auto-repair feature.
- The Rust and Python failures preserve any copied-but-unregistered files
  rather than risking the wrong unlink; future UI should expose a local,
  owner-approved reconciliation flow after checking live hashes.
- A **real Windows cross-language process test** now launches Python
  3.12 as a child process of the Rust native test runner and uses the
  actual `model_manifest_lock.exclusive_manifest_write` implementation.
  It checks Python-held lock blocks a Rust registry update and Rust-held
  lock blocks the Python guard. This is a disposable CI fixture test,
  not an installed GUI end-to-end test or malicious filesystem audit.
- M2 cross-language manifest preservation QA now runs the **real**
  Python Pydantic-backed `save_manifest_entry` writer against native Rust
  `record_snapshot` in a disposable Windows temp root. A Rust lock is
  held while Python is ready; Python must not commit early. After release,
  Python writes its record and Rust writes a third, and the test requires
  all **three fake registry entries** to survive. This requires
  `backend/requirements.txt` in the Windows Rust CI runner (for Pydantic).
  It still does NOT certify malicious cross-user locking or full
  transactional crash recovery.
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
- [ ] New Windows no-follow fixture test and bidirectional Python/Rust
  child-process guard test pass exact-head Rust CI. Review that the
  limited scope is not overstated as safe arbitrary-path access.
- [ ] Handle-relative root/ancestor traversal and malicious concurrent
  replacement defense remain separate production security blockers.
- [ ] Human security review / branch protection / owner-approved
  integration remain blockers in Issue #60.

References:

- [Microsoft Win32 reparse points](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points-and-file-operations)
- [Python msvcrt and file operations](https://docs.python.org/3/library/msvcrt.html)
- [Rust std::fs::File and locking](https://doc.rust-lang.org/std/fs/struct.File.html)
- [Tauri 2 app command capabilities](https://v2.tauri.app/security/capabilities/)
