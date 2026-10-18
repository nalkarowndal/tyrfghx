# M3-37 — Deterministic real Windows model catalog failure and retry

## Objective

M3-36's [normal CI](https://github.com/nalkarowndal/tyrfghx/actions/runs/39139182087)
and [real embedded Windows GUI E2E](https://github.com/nalkarowndal/tyrfghx/actions/runs/39139283026)
both passed. Previously `catalog_error_recovery` was always `not_exercised`
because the native catalog did not happen to fail on disposable CI.

M3-37 adds a controlled real native IPC failure and real GUI retry. It does
not corrupt or alter private models, change registry files, invoke a model
picker, load weights, enable GPU compute or authorize inference.

## Mechanism and security boundaries

- The one-shot injector exists only under the Cargo feature
  `e2e-webdriver`. The normal production feature set does not compile it.
- It additionally requires `AIIMAGE_E2E_ENABLE=1` and a
  `AIIMAGE_E2E_CATALOG_FAILURE_MARKER` path set by the owned Node UI test.
- The marker must be an ordinary non-symlink file directly in the canonical
  OS temporary folder, named `aiimage-e2e-catalog-<random UUID>.sentinel`,
  containing exactly the fixed text `aiimage-e2e-fail-once\n`.
  Other paths, malformed contents, unexpectedly large files and symlinks
  are ignored. The test deletes only its own random marker if it wasn't
  consumed.
- Only after the embedded Tauri app's initial catalog has settled does the
  test create the marker, then click the actual **목록 새로고침** button.
- The next `list_local_models` native IPC returns one synthetic error
  **after consuming the marker**. This uses Tauri's normal `Result::Err`
  to make frontend `invoke` reject, exercising the real catalog recovery
  pathway.
- UI E2E requires the visible model-catalog error, **zero stale model cards**
  and exactly one successful manual retry. If the error is absent, the test
  fails rather than claiming a false pass.
- After retry, the existing release-only native GPU policy/consent/
  missing-checkpoint controls are checked again.
- The existing ordinary no-fault GUI acceptance stays a separate preceding
  step, so normal usage isn't forced to encounter an artificial error.

## Tests

The regular frontend Node W3C fake-server tests now cover an explicitly
requested failure that is observed and recovered, an absent expected failure
(fail-closed), and rejection of synthetic faults in external-driver mode.
Normal CI also runs the existing Windows Rust `cargo test --locked` and
Python/React tests.

An **explicitly opted-in**, same-repository Windows workflow executes:

```powershell
node scripts/windows-ui-e2e.mjs --run --embedded
node scripts/windows-ui-e2e.mjs --run --embedded --catalog-fault-once
```

It does not upload E2E test binaries or screenshots. The ordinary production
release still has no embedded HTTP WebDriver and no fault-injection code.
The feature-enabled binary remains a disposable test-only artifact.

## Verification criteria

`catalog_error_recovery: passed` in the second **real Windows** run,
with all other release safety checks passed, is required to call this stage
fully verified. Mock W3C tests alone or a skipped opt-in workflow are not
sufficient. The GUI error message is synthetic, but the app uses the actual
Tauri IPC, React loading/error state and user-facing retry button.

Real model data corruption, model import dialog failure, real GPU/RTX 2060
SUPER inference, Windows installer, signing and packaged Python backend are
separate work.
